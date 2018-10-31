import os
from flask import Flask, render_template, request
import stripe

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}


stripe.api_key = stripe_keys['secret_key']

app = Flask(__name__)

@app.route('/<int:amount>/')
def index(amount):
    return render_template('index.html', key=stripe_keys['publishable_key'], amount=amount)



@app.route('/charge', methods=['POST'])
def charge():
    # Amount in cents
    # amount = request.form['data-amount']
    # description = request.form['data-amount']
    amount = 500
 	description = "test"

    customer = stripe.Customer.create(
        email='customer@example.com',
        source=request.form['stripeToken']
    )

    charge = stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency='usd',
        description=description
    )

    return render_template('charge.html', amount=amount)

if __name__ == '__main__':
    app.run(debug=True)