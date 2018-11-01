import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import stripe

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}

stripe.api_key = stripe_keys['secret_key']

app = Flask(__name__)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route('/')
def redirect_to_give():
    return redirect(url_for('.give', dollars=20, _external=True), code=302)

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

@app.before_request
def redirect_to_cdn():
    if app.debug or app.testing:
        return None
    url = request.url
    if url.startswith('http://'):
        url = url.replace('http://', 'https://', 1)
    if url.startswith('https://mb-text-donation.azurewebsites.net'):
        url = url.replace(
            'https://mb-text-donation.azurewebsites.net',
            'https://donate.missionbit.org',
            1
        )
        app.config['SERVER_NAME'] = 'donate.missionbit.org'
    if url == request.url:
        return None
    return redirect(url, code=302)

if __name__ == '__main__':
    app.run(debug=True)
