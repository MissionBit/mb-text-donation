import os
import logging
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.contrib.fixers import ProxyFix
import stripe

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}

stripe.api_key = stripe_keys['secret_key']

CANONICAL_HOST = os.environ['CANONICAL_HOST']

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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('default.html', key=stripe_keys['publishable_key']), 200

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route('/')
def redirect_to_give():
    return redirect('/20/', code=302)

@app.route('/<int:dollars>/')
def give(dollars):
    return render_template(
        'index.html',
        key=stripe_keys['publishable_key'],
        amount=dollars * 100
    )

@app.route('/charge', methods=['POST'])
def charge():
    amount = request.form.get('amount', type=int)

    customer = stripe.Customer.create(
        email=request.form['stripeEmail'],
        source=request.form['stripeToken']
    )

    stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency='USD',
        description='Donation'
    )

    return render_template('charge.html', amount=amount)

if CANONICAL_HOST:
    @app.before_request
    def redirect_to_cdn():
        o = urlsplit(request.url)
        if o.scheme == 'https' and o.netloc == CANONICAL_HOST:
            return None
        url = urlunsplit(('https', CANONICAL_HOST, o[2], o[3], o[4]))
        app.logger.info('REDIRECT {}://{} to {}'.format(o.scheme, o.netloc, url))
        return redirect(url, code=302)

if __name__ == '__main__':
    app.run(debug=True)
