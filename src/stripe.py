import stripe
stripe.api_key = "pk_test_RSXDz0BWdbmCFT8VSY24fikA"


def new_customer(phone, donation_amount, recurrence_interval):
	customer = stripe.Customer.create(
	  description="Customer for jenny.rosen@example.com",
	  source="tok_amex" # obtained with Stripe.js
	)
	
	return 