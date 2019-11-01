import os
import re
import time
import logging
import hashlib
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, abort
from werkzeug.contrib.fixers import ProxyFix
import stripe
import sendgrid
from jsonschema import validate
from parse_cents import parse_cents
from python_http_client import exceptions
from applicationinsights.flask.ext import AppInsights

try:
    if 'WEBSITE_SITE_NAME' in os.environ:
        os.environ['GIT_VERSION'] = open('../repository/.git/refs/heads/master', 'r').read()
except OSError:
    pass

RECEIPT_TEMPLATE_ID = 'd-7e5e6a89f9284d2ab01d6c1e27a180f8'
SENDGRID_API_KEY = os.environ['SENDGRID_API_KEY']
DONATE_EMAIL = "donate@missionbit.com"

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY'],
  'endpoint_secret': os.environ['WEBHOOK_SIGNING_SECRET']
}

stripe.api_key = stripe_keys['secret_key']

CANONICAL_HOSTS = os.environ.get('CANONICAL_HOST', '').split()

CHECKOUT_SCHEMA = {
    "type": "object",
    "description": "Start the Stripe checkout flow",
    "required": ["amount"],
    "properties": {
        "amount": {
            "type": "integer",
            "description": "USD cents of donation",
            "minimum": 100
        },
        "metadata": {"type": "object"}
    }
}

def verizonProxyHostFixer(app):
    """Azure's Verizon Premium CDN uses the header X-Host instead of X-Forwarded-Host
    """
    def proxy_fixed_app(environ, start_response):
        x_host = os.environ.get('HTTP_X_HOST')
        if x_host in CANONICAL_HOSTS:
            environ['HTTP_X_FORWARDED_HOST'] = x_host
        return app(environ, start_response)
    return proxy_fixed_app

app = Flask(__name__)
appinsights = AppInsights(app)
if CANONICAL_HOSTS:
    app.wsgi_app = verizonProxyHostFixer(ProxyFix(app.wsgi_app))
streamHandler = logging.StreamHandler()
app.logger.addHandler(streamHandler)
app.logger.setLevel(logging.DEBUG)

def get_telemetry_client():
    requests_middleware = appinsights._requests_middleware
    return requests_middleware.client if requests_middleware else None

def set_default_app_context():
    requests_middleware = appinsights._requests_middleware
    if requests_middleware:
        envs = [
            'WEBSITE_SITE_NAME',
            'GIT_VERSION'
        ]
        for k in envs:
            v = os.environ.get(k)
            if v:
                requests_middleware._common_properties[k] = v

set_default_app_context()

def merge_dicts(*dicts):
    rval = {}
    for d in dicts:
        if d:
            rval.update(d)
    return rval

@app.template_filter('asset_url')
def asset_url(path, CACHE={}):
    abspath = os.path.abspath(app.root_path + path)
    # Avoid directory traversal mistakes
    if not abspath.startswith(app.static_folder):
        return path
    try:
        # Check that the file exists and use its
        # size and creation time as a cache key to avoid
        # computing a digest on every request
        stat = os.stat(abspath)
        key = stat.st_size, stat.st_mtime
        cached = CACHE.get(path)
        if cached is not None and CACHE[0] == key:
            return cached[1]
        # Get a SHA1 digest of the file contents
        h = hashlib.sha1()
        with open(abspath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                h.update(chunk)
        # Use the prefix of the digest in the URL to ensure
        # the browser will receive the latest version
        rval = '{}?v={}'.format(path, h.hexdigest()[:8])
        CACHE[path] = (key, rval)
        return rval
    except OSError:
        # This will catch any FileNotFoundError or similar
        # issues with stat, open, or read.
        return path

@app.after_request
def add_cache_control_header(response):
    """Disable caching for non-static endpoints
    """
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route('/robots.txt')
def robots():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'robots.txt',
        mimetype='text/plain'
    )

@app.route('/.well-known/apple-developer-merchantid-domain-association')
def apple_pay_domain_association():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'apple-developer-merchantid-domain-association',
        mimetype='text/plain'
    )

def format_identifier(s):
    """
    >>> format_identifier('apple_pay')
    'Apple Pay'
    """
    return ' '.join(map(lambda s: s.capitalize(), s.split('_')))

CARD_BRANDS = {
    'amex': 'American Express',
    'diners': 'Diners Club',
    'discover': 'Discover',
    'jcb': 'JCB',
    'mastercard': 'Mastercard',
    'unionpay': 'UnionPay',
    'visa': 'Visa'
}

def format_charge_source(charge):
    payment_method_details = charge.payment_method_details
    payment_type = payment_method_details.type
    if payment_type in ("card", "card_present"):
        details = payment_method_details[payment_type]
        parts = []
        brand = CARD_BRANDS.get(details.brand)
        if brand:
            parts.append(brand)
        if details.funding != "unknown":
            parts.append(details.funding)
        parts.append('card')
        if details.wallet:
            parts.append('({})'.format(format_identifier(details.wallet.type)))
        return ' '.join(parts)
    else:
        return format_identifier(payment_type)

def sendgrid_safe_name(name):
    """The to.name, cc.name, and bcc.name personalizations cannot include either the ; or , characters.
    """
    return re.sub(r'([,;]\s*)+', ' ', name)

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect('/')
    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=['payment_intent']
    )
    charge = session.payment_intent.charges.data[0]

    client = get_telemetry_client()
    if client:
        client.track_event(
            'Donation',
            merge_dicts(charge.get('metadata'), {
                'email': charge.billing_details.email,
                'name': charge.billing_details.name,
                'id': charge.id,
                'payment_method': format_charge_source(charge)
            }),
            {
                'amount': charge.amount
            }
        )

    return render_template(
        'success.html',
        name=charge.billing_details.name,
        email=charge.billing_details.email,
        amount=charge.amount,
        payment_method=format_charge_source(charge),
        id=charge.id,
        donate_email=DONATE_EMAIL
    )

@app.route('/checkout', methods=['POST'])
def checkout():
    body = request.json
    validate(body, CHECKOUT_SCHEMA)
    amount = body['amount']
    o = urlsplit(request.url)
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        success_url=urlunsplit((o.scheme, o.netloc, '/success', 'session_id={CHECKOUT_SESSION_ID}', '')),
        cancel_url=urlunsplit((o.scheme, o.netloc, '/cancel', '', '')),
        billing_address_collection='required',
        payment_intent_data={
            "metadata": body.get('metadata', {})
        },
        line_items=[
            {
                "amount": amount,
                "currency": "USD",
                "name": "One-time donation",
                "quantity": 1
            }
        ],
        submit_type="donate"
    )
    return jsonify(sessionId=session.id)

def stripe_checkout_session_completed(session):
    payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)
    charge = payment_intent.charges.data[0]

    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    try:
        response = sg.send({
            "template_id": RECEIPT_TEMPLATE_ID,
            "from": {
                "name": "Mission Bit",
                "email": DONATE_EMAIL
            },
            "personalizations": [
                {
                    "to": [
                        {
                            "name": sendgrid_safe_name(charge.billing_details.name),
                            "email": charge.billing_details.email
                        }
                    ],
                    "dynamic_template_data": {
                        "transaction_id": charge.id,
                        "total": '${:,.2f}'.format(charge.amount * 0.01),
                        "date": time.strftime('%x', time.gmtime(charge.created)),
                        "payment_method": format_charge_source(charge)
                    }
                }
            ]
        })
        if not (200 <= response.status_code < 300):
            return abort(400)
    except exceptions.BadRequestsError:
        return abort(400)
    client = get_telemetry_client()
    if client:
        client.track_event(
            'Donation',
            merge_dicts(payment_intent.metadata, {
                'email': charge.billing_details.email,
                'name': charge.billing_details.name,
                'id': charge.id,
                'payment_method': format_charge_source(charge)
            }),
            {
                'amount': charge.amount
            }
        )

@app.route('/hooks', methods=['POST'])
def stripe_webhook():
    payload = request.data.decode("utf-8")
    sig_header = request.headers.get("Stripe-Signature", None)
    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_keys['endpoint_secret']
        )
    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400
    if event['type'] == 'checkout.session.completed':
        stripe_checkout_session_completed(event['data']['object'])
    return "", 200

@app.route('/')
@app.route('/<dollars>')
@app.route('/<dollars>/')
def index(dollars=''):
    return render_template(
        'index.html',
        key=stripe_keys['publishable_key'],
        metadata=merge_dicts(
            request.args,
            { 'host': urlsplit(request.url).netloc }
        ),
        amount=parse_cents(dollars)
    )

if CANONICAL_HOSTS:
    @app.before_request
    def redirect_to_cdn():
        o = urlsplit(request.url)
        if o.scheme == 'https' and o.netloc in CANONICAL_HOSTS:
            return None
        url = urlunsplit(('https', CANONICAL_HOSTS[0], o[2], o[3], o[4]))
        return redirect(url, code=302)

if __name__ == '__main__':
    app.run(debug=True)
