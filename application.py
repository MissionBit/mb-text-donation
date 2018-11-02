import os
from flask import Flask, render_template, request
import stripe

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}


stripe.api_key = stripe_keys['secret_key']

app = Flask(__name__)

@app.route('/<int:message>/')
def index(message):
    return render_template('index.html', key=stripe_keys['publishable_key'], amount=100*message)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('default.html', key=stripe_keys['publishable_key']), 200

@app.route('/charge', methods=['POST'])
def charge():
    amount = request.form.get('amount', type=float)
    amount = int(amount * 100);


    customer = stripe.Customer.create(
        email=request.form['stripeEmail'],
        source=request.form['stripeToken']
    )

    charge = stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency='USD',
        description='Donation'
    )

    return render_template('charge.html', amount=amount)

if __name__ == '__main__':
    app.run(debug=True)