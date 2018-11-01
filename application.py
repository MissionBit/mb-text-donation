import os
from flask import Flask, render_template, request
import stripe

stripe_keys = {
  'secret_key': os.environ['SECRET_KEY'],
  'publishable_key': os.environ['PUBLISHABLE_KEY']
}


stripe.api_key = stripe_keys['secret_key']

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
  return app.send_static_file('data.json')

@app.route('/donate/<int:message>/')
def donate(message):
    return render_template('donate.html', key=stripe_keys['publishable_key'], amount=100*message)

@app.route('/charge', methods=['POST'])
def charge():
    amount = request.form.get('amount', type=int)

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