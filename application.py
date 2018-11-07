import os
import re
import time
import logging
import hashlib
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from werkzeug.contrib.fixers import ProxyFix
import stripe
import sendgrid
from jsonschema import validate
from parse_cents import parse_cents
from python_http_client import exceptions

RECEIPT_TEMPLATE_ID = 'd-7e5e6a89f9284d2ab01d6c1e27a180f8'
SENDGRID_API_KEY = os.environ['SENDGRID_API_KEY']

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}

stripe.api_key = stripe_keys['secret_key']

CANONICAL_HOST = os.environ.get('CANONICAL_HOST')

CHARGE_SCHEMA = {
    "type": "object",
    "description": "A donation to be collected",
    "properties": {
        "amount": {
            "type": "integer",
            "description": "USD cents of donation",
            "minimum": 100
        },
        "token": {
            "type": "object",
            "description": "Stripe token",
            "properties": {
                "email": { "type": "string" },
                "id": { "type": "string" }
            }
        }
    }
}

def verizonProxyHostFixer(app):
    """Azure's Verizon Premium CDN uses the header X-Host instead of X-Forwarded-Host
    """
    def proxy_fixed_app(environ, start_response):
        if environ.get('HTTP_X_HOST') == CANONICAL_HOST:
            environ['HTTP_X_FORWARDED_HOST'] = CANONICAL_HOST
        return app(environ, start_response)
    return proxy_fixed_app

app = Flask(__name__)
if CANONICAL_HOST:
    app.wsgi_app = verizonProxyHostFixer(ProxyFix(app.wsgi_app))
streamHandler = logging.StreamHandler()
app.logger.addHandler(streamHandler)
app.logger.setLevel(logging.DEBUG)

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
        CACHE[path] = key, rval
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

@app.route('/.well-known/apple-developer-merchantid-domain-association')
def apple_pay_domain_association():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'apple-developer-merchantid-domain-association',
        mimetype='text/plain'
    )

@app.route('/')
@app.route('/<dollars>/')
def index(dollars=''):
    return render_template(
        'index.html',
        key=stripe_keys['publishable_key'],
        amount=parse_cents(dollars)
    )

def format_identifier(s):
    """
    >>> format_identifier('apple_pay')
    'Apple Pay'
    """
    return ' '.join(map(lambda s: s.capitalize(), s.split('_')))

def format_source(source):
    parts = []
    if source['object'] == 'card':
        if source['brand'] != 'Unknown':
            parts.append(source['brand'])
        if source['funding'] != 'unknown':
            parts.append(source['funding'])
        parts.append('card')
        if source['tokenization_method']:
            parts.append(
                '({})'.format(
                    format_identifier(source['tokenization_method'])
                )
            )
    return ' '.join(parts) or 'Unknown'

@app.route('/charge', methods=['POST'])
def charge():
    body = request.json
    validate(body, CHARGE_SCHEMA)
    amount = body['amount']
    token = body['token']
    customer = stripe.Customer.create(
        email=token['email'],
        source=token['id']
    )
    charge = stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency='USD',
        description='Donation'
    )
    sg = sendgrid.SendGridAPIClient(apikey=SENDGRID_API_KEY)
    email_sent = False
    try:
        response = sg.client.mail.send.post(request_body={
            "template_id": RECEIPT_TEMPLATE_ID,
            "from": {
                "email": "donate@missionbit.com"
            },
            "personalizations": [
                {
                    "to": [
                        { "email": customer.email }
                    ],
                    "dynamic_template_data": {
                        "transaction_id": charge.id,
                        "total": '${:,.2f}'.format(charge.amount * 0.01),
                        "date": time.strftime('%x', time.gmtime(charge.created)),
                        "payment_method": format_source(charge.source)
                    }
                }
            ]
        })
        email_sent = 200 <= response.status_code < 300
    except exceptions.BadRequestsError:
        pass

    return jsonify(
        email_sent=email_sent,
        email=customer.email,
        amount=amount,
        id=charge.id
    )

if CANONICAL_HOST:
    @app.before_request
    def redirect_to_cdn():
        o = urlsplit(request.url)
        if o.scheme == 'https' and o.netloc == CANONICAL_HOST:
            return None
        url = urlunsplit(('https', CANONICAL_HOST, o[2], o[3], o[4]))
        return redirect(url, code=302)

if __name__ == '__main__':
    app.run(debug=True)
