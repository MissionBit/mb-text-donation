import os
import re
import sys
import time
import traceback
import logging
import hashlib
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime
from dateutil import tz
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    jsonify,
    abort,
)
from werkzeug.middleware.proxy_fix import ProxyFix
import stripe
import sendgrid
from jsonschema import validate
from parse_cents import parse_cents
from python_http_client import exceptions
from applicationinsights.flask.ext import AppInsights

try:
    if "WEBSITE_SITE_NAME" in os.environ:
        os.environ["GIT_VERSION"] = open(
            "../repository/.git/refs/heads/master", "r"
        ).read()
except OSError:
    pass

TEST_ENVIRONMENT = os.path.basename(sys.argv[0]) == "pytest"
REDIRECT_TO_WWW = os.environ.get("REDIRECT_TO_WWW") != "false"


def require_env(k: str) -> str:
    v = os.environ.get(k)
    if v is None:
        if TEST_ENVIRONMENT:
            return f"TEST_{k}"
        else:
            raise KeyError(f"Missing required environment variable {k}")
    return v


RECEIPT_TEMPLATE_ID = "d-7e5e6a89f9284d2ab01d6c1e27a180f8"
FAILURE_TEMPLATE_ID = "d-570b4b8b20e74ec5a9c55be7e07e2665"
SENDGRID_API_KEY = require_env("SENDGRID_API_KEY")
DONATE_EMAIL = "donate@missionbit.org"
MONTHLY_PLAN_ID = "mb-monthly-001"
LOCAL_TZ = tz.gettz("America/Los_Angeles")

stripe_keys = {
    "secret_key": require_env("SECRET_KEY"),
    "publishable_key": require_env("PUBLISHABLE_KEY"),
    "endpoint_secret": require_env("WEBHOOK_SIGNING_SECRET"),
}

stripe.api_key = stripe_keys["secret_key"]

CANONICAL_HOSTS = os.environ.get("CANONICAL_HOST", "").split()

CHECKOUT_SCHEMA = {
    "type": "object",
    "description": "Start the Stripe checkout flow",
    "required": ["amount"],
    "properties": {
        "amount": {
            "type": "integer",
            "description": "USD cents of donation",
            "minimum": 100,
        },
        "metadata": {"type": "object"},
    },
}


def verizonProxyHostFixer(app):
    """Azure's Verizon Premium CDN uses the header X-Host instead of X-Forwarded-Host
    """

    def proxy_fixed_app(environ, start_response):
        x_host = environ.get("HTTP_X_HOST")
        if x_host in CANONICAL_HOSTS:
            environ["HTTP_X_FORWARDED_HOST"] = x_host
        return app(environ, start_response)

    return proxy_fixed_app


app = Flask(__name__)
appinsights = AppInsights(app)
if CANONICAL_HOSTS:
    # Azure's Verizon Premium CDN uses the header X-Host instead of X-Forwarded-Host
    app.wsgi_app = verizonProxyHostFixer(ProxyFix(app.wsgi_app, x_host=1))
streamHandler = logging.StreamHandler()
app.logger.addHandler(streamHandler)
app.logger.setLevel(logging.DEBUG)


def get_telemetry_client():
    requests_middleware = appinsights._requests_middleware
    return requests_middleware.client if requests_middleware else None


def set_default_app_context():
    requests_middleware = appinsights._requests_middleware
    if requests_middleware:
        envs = ["WEBSITE_SITE_NAME", "GIT_VERSION"]
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


@app.template_filter("asset_url")
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
        if cached is not None and cached[0] == key:
            return cached[1]
        # Get a SHA1 digest of the file contents
        h = hashlib.sha1()
        with open(abspath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        # Use the prefix of the digest in the URL to ensure
        # the browser will receive the latest version
        rval = "{}?v={}".format(path, h.hexdigest()[:8])
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
    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/robots.txt")
def robots():
    return send_from_directory(
        os.path.join(app.root_path, "static"), "robots.txt", mimetype="text/plain"
    )


@app.route("/.well-known/apple-developer-merchantid-domain-association")
def apple_pay_domain_association():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "apple-developer-merchantid-domain-association",
        mimetype="text/plain",
    )


def format_identifier(s):
    """
    >>> format_identifier('apple_pay')
    'Apple Pay'
    """
    return " ".join(map(lambda s: s.capitalize(), s.split("_")))


CARD_BRANDS = {
    "amex": "American Express",
    "diners": "Diners Club",
    "discover": "Discover",
    "jcb": "JCB",
    "mastercard": "Mastercard",
    "unionpay": "UnionPay",
    "visa": "Visa",
}


def format_payment_method_details_source(payment_method_details):
    payment_type = payment_method_details.type
    if payment_type in ("card", "card_present"):
        details = payment_method_details[payment_type]
        parts = []
        brand = CARD_BRANDS.get(details.brand)
        if brand:
            parts.append(brand)
        if details.funding != "unknown":
            parts.append(details.funding)
        parts.append("card")
        if details.wallet:
            parts.append("({})".format(format_identifier(details.wallet.type)))
        return " ".join(parts)
    else:
        return format_identifier(payment_type)


def sendgrid_safe_name(name):
    """The to.name, cc.name, and bcc.name personalizations cannot include either the ; or , characters.
    """
    return re.sub(r"([,;]\s*)+", " ", name)


@app.route("/cancel")
def cancel():
    return render_template("cancel.html", donate_email=DONATE_EMAIL)


@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        return redirect("/")
    session = stripe.checkout.Session.retrieve(
        session_id, expand=["payment_intent", "subscription.default_payment_method"]
    )
    return render_template(
        "success.html", donate_email=DONATE_EMAIL, **session_info(session)
    )


def session_info(session):
    if session.mode == "subscription":
        subscription = session.subscription
        pm = subscription.default_payment_method
        return merge_dicts(
            {
                "id": subscription.id,
                "frequency": "monthly",
                "amount": subscription.plan.amount * subscription.quantity,
                "payment_method": format_payment_method_details_source(pm),
            },
            billing_details_to(pm.billing_details),
        )
    elif session.mode == "payment":
        charge = session.payment_intent.charges.data[0]
        return merge_dicts(
            {
                "id": charge.id,
                "frequency": "one-time",
                "amount": charge.amount,
                "payment_method": format_payment_method_details_source(
                    charge.payment_method_details
                ),
            },
            billing_details_to(charge.billing_details),
        )
    else:
        raise NotImplementedError


def session_kw(amount, frequency, metadata):
    if frequency == "monthly":
        return {
            "mode": "subscription",
            "subscription_data": {
                "items": [{"plan": MONTHLY_PLAN_ID, "quantity": amount}],
                "metadata": metadata,
            },
        }
    else:
        return {
            "mode": "payment",
            "line_items": [
                {
                    "amount": amount,
                    "currency": "USD",
                    "name": "One-time donation",
                    "quantity": 1,
                }
            ],
            "submit_type": "donate",
            "payment_intent_data": {"description": "Donation", "metadata": metadata},
        }


@app.route("/checkout", methods=["POST"])
def checkout():
    body = request.json
    validate(body, CHECKOUT_SCHEMA)
    amount = body["amount"]
    frequency = body["frequency"]
    o = urlsplit(request.url)
    metadata = merge_dicts(
        body.get("metadata", {}),
        {"origin": urlunsplit((o.scheme, o.netloc, "", "", ""))},
    )
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        success_url=urlunsplit(
            (o.scheme, o.netloc, "/success", "session_id={CHECKOUT_SESSION_ID}", "")
        ),
        cancel_url=urlunsplit((o.scheme, o.netloc, "/cancel", "", "")),
        **session_kw(amount=amount, frequency=frequency, metadata=metadata),
    )
    return jsonify(sessionId=session.id)


def billing_details_to(billing_details):
    return {
        "name": sendgrid_safe_name(billing_details.name),
        "email": billing_details.email,
    }


def donor_name(billing_details):
    if billing_details.name:
        return f"{billing_details.name} <{billing_details.email}>"
    else:
        return billing_details.email


def stripe_checkout_session_completed(session):
    # Subscription receipts are handled by invoice payments
    if session.mode == "payment":
        return stripe_checkout_session_completed_payment(
            stripe.checkout.Session.retrieve(session.id, expand=["payment_intent"])
        )


def get_origin(metadata):
    return metadata.get(
        "origin",
        f"https://{CANONICAL_HOSTS[0]}" if CANONICAL_HOSTS else "http://localhost:5000",
    )


def stripe_invoice_payment_succeeded(invoice):
    invoice = stripe.Invoice.retrieve(
        invoice.id, expand=["subscription", "payment_intent"]
    )
    subscription = invoice.subscription
    charge = invoice.payment_intent.charges.data[0]
    if is_from_new_app(subscription.metadata):
        print(f"Skipping subscription email from new app: {charge.id}")
        return
    next_dt = datetime.fromtimestamp(subscription.current_period_end, LOCAL_TZ)
    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    try:
        response = sg.send(
            email_template_data(
                template_id=RECEIPT_TEMPLATE_ID,
                charge=charge,
                frequency="monthly",
                monthly={
                    "next": f"{next_dt.strftime('%b')} {next_dt.day}, {next_dt.year}",
                    "url": f"{get_origin(subscription.metadata)}/subscriptions/{subscription.id}",
                },
            )
        )
        if not (200 <= response.status_code < 300):
            return abort(400)
    except exceptions.BadRequestsError:

        return abort(400)
    track_donation(metadata=subscription.metadata, frequency="monthly", charge=charge)


def email_template_data(template_id, charge, frequency, **kw):
    payment_method = format_payment_method_details_source(charge.payment_method_details)
    return {
        "template_id": template_id,
        "from": {"name": "Mission Bit", "email": DONATE_EMAIL},
        "personalizations": [
            {
                "to": [billing_details_to(charge.billing_details)],
                "dynamic_template_data": merge_dicts(
                    {
                        "transaction_id": charge.id,
                        "frequency": frequency,
                        "total": "${:,.2f}".format(charge.amount * 0.01),
                        "date": datetime.fromtimestamp(
                            charge.created, LOCAL_TZ
                        ).strftime("%x"),
                        "payment_method": payment_method,
                        "donor": donor_name(charge.billing_details),
                    },
                    kw,
                ),
            }
        ],
    }


def track_invoice_failure(metadata, frequency, charge):
    client = get_telemetry_client()
    if client is None:
        return
    payment_method = format_payment_method_details_source(charge.payment_method_details)
    client.track_event(
        "DonationFailed",
        merge_dicts(
            metadata,
            billing_details_to(charge.billing_details),
            {"id": charge.id, "frequency": frequency, "payment_method": payment_method},
        ),
        {"amount": charge.amount},
    )


def track_donation(metadata, frequency, charge):
    client = get_telemetry_client()
    if client is None:
        return
    payment_method = format_payment_method_details_source(charge.payment_method_details)
    client.track_event(
        "Donation",
        merge_dicts(
            metadata,
            billing_details_to(charge.billing_details),
            {"id": charge.id, "frequency": frequency, "payment_method": payment_method},
        ),
        {"amount": charge.amount},
    )


def stripe_checkout_session_completed_payment(session):
    payment_intent = session.payment_intent
    charge = payment_intent.charges.data[0]
    payment_method = format_payment_method_details_source(charge.payment_method_details)
    if is_from_new_app(payment_intent.metadata):
        print(f"Skipping charge email from new app: {charge.id}")
        return
    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    try:
        response = sg.send(
            email_template_data(
                template_id=RECEIPT_TEMPLATE_ID, charge=charge, frequency="one-time"
            )
        )
        if not (200 <= response.status_code < 300):
            print(repr(response))
            return abort(400)
    except exceptions.BadRequestsError:
        traceback.print_tb(sys.last_traceback)
        return abort(400)
    track_donation(
        metadata=payment_intent.metadata, frequency="one-time", charge=charge
    )


def stripe_invoice_payment_failed(invoice):
    invoice = stripe.Invoice.retrieve(
        invoice.id, expand=["subscription", "payment_intent"]
    )
    if invoice.billing_reason != "subscription_cycle":
        # No email unless it's a renewal, they got an error in the
        # Stripe Checkout UX for new subscriptions.
        return
    subscription = invoice.subscription
    charge = invoice.payment_intent.charges.data[0]
    if is_from_new_app(subscription.metadata):
        print(f"Skipping subscription failure email from new app: {charge.id}")
        return
    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    origin = get_origin(subscription.metadata)
    try:
        response = sg.send(
            email_template_data(
                template_id=FAILURE_TEMPLATE_ID,
                charge=charge,
                frequency="monthly",
                failure_message=charge.failure_message,
                renew_url=f"{origin}/{'${:,.2f}'.format(charge.amount * 0.01)}/?frequency=monthly",
                subscription_id=subscription.id,
                subscription_url=f"{origin}/subscriptions/{subscription.id}",
            )
        )
        if not (200 <= response.status_code < 300):
            return abort(400)
    except exceptions.BadRequestsError:
        return abort(400)
    # Cancel the subscription to avoid future charges
    if subscription.status != "canceled":
        stripe.Subscription.delete(subscription.id)
    track_invoice_failure(
        metadata=subscription.metadata, frequency="monthly", charge=charge
    )

def is_from_new_app(metadata):
    """Events created by the new www.missionbit.org donation portal should be ignored
    """
    return metadata.get("app") == "www.missionbit.org"

@app.route("/hooks", methods=["POST"])
def stripe_webhook():
    payload = request.data.decode("utf-8")
    sig_header = request.headers.get("Stripe-Signature", None)
    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=stripe_keys["endpoint_secret"],
        )
    except ValueError as e:
        # Invalid payload
        print("Invalid hook payload")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print("Invalid hook signature")
        return "Invalid signature", 400
    handlers = {
        "checkout.session.completed": stripe_checkout_session_completed,
        "invoice.payment_succeeded": stripe_invoice_payment_succeeded,
        "invoice.payment_failed": stripe_invoice_payment_failed,
    }
    handler = handlers.get(event["type"])
    if handler is not None:
        obj = event["data"]["object"]
        print(f"handling {event['type']} id: {obj.id}")
        handler(obj)
    else:
        print(f"{event['type']} not handled")
    return jsonify({"status": "success"})


def host_default_amount(host):
    if host.startswith("gala."):
        return "$250"
    else:
        return "$50"


@app.route("/subscriptions/<subscription_id>")
def subscription(subscription_id):
    if REDIRECT_TO_WWW:
        return redirect(f"https://www.missionbit.org/donate/subscriptions/{subscription_id}")
    try:
        subscription = stripe.Subscription.retrieve(
            subscription_id, expand=["default_payment_method"]
        )
    except stripe.error.InvalidRequestError:
        return redirect("/")
    pm = subscription.default_payment_method
    next_dt = datetime.fromtimestamp(subscription.current_period_end, LOCAL_TZ)
    return render_template(
        "subscription.html",
        donate_email=DONATE_EMAIL,
        subscription=subscription,
        id=subscription.id,
        frequency="monthly",
        amount=subscription.plan.amount * subscription.quantity,
        payment_method=format_payment_method_details_source(pm),
        next_cycle=f"{next_dt.strftime('%b')} {next_dt.day}, {next_dt.year}",
        **billing_details_to(pm.billing_details),
    )


@app.route("/subscriptions/<subscription_id>", methods=["POST"])
def delete_subscription(subscription_id):
    try:
        stripe.Subscription.delete(subscription_id)
    except stripe.error.InvalidRequestError:
        return redirect(f"/subscriptions/{subscription_id}")
    return redirect(f"/subscriptions/{subscription_id}")


@app.route("/")
@app.route("/<dollars>")
@app.route("/<dollars>/")
def index(dollars=""):
    if REDIRECT_TO_WWW:
        return redirect("https://www.missionbit.org/donate")
    host = urlsplit(request.url).netloc
    frequency = (
        "monthly" if request.args.get("frequency", "once") == "monthly" else "once"
    )
    amount = parse_cents(dollars) or parse_cents(host_default_amount(host))
    return render_template(
        "index.html",
        key=stripe_keys["publishable_key"],
        metadata=merge_dicts(request.args, {"host": host}),
        frequency=frequency,
        formatted_dollar_amount="{:.2f}".format(amount * 0.01)
        if amount % 100
        else f"{amount // 100}",
    )


if CANONICAL_HOSTS:

    @app.before_request
    def redirect_to_cdn():
        o = urlsplit(request.url)
        redirect_host = CANONICAL_HOSTS[0]
        if o.netloc in CANONICAL_HOSTS:
            if o.scheme == "https":
                return None
            else:
                redirect_host = o.netloc
        url = urlunsplit(("https", redirect_host, o[2], o[3], o[4]))
        return redirect(url, code=302)


if __name__ == "__main__":
    app.run(debug=True)
