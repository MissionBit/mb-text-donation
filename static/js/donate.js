"use strict";

(function () {
  function onToken(e) {
    console.log(e);
    completeDonation({
      token: e.token.id,
      type: 'paymentRequest',
      amount: amount
    }).then(
      function () {
        e.complete('success');
        donationCompleted();
      },
      function () {
        e.complete('fail');
        donationFailed();
      }
    );
  }

  function onCancel(e) {
    console.log(e);
  }

  function donationCompleted() {
    console.log('completed');
  }

  function donationFailed() {
    console.log('failed');
  }

  function completeDonation(opts) {
    console.log(opts);
    return Promise.reject(new Error('Not Implemented'));
  }

  function parseCents(s) {
    var m = /^\s*\$?([1-9]\d*)((?:,\d\d\d)*)(?:\.(\d\d))?\s*$/.exec(amountRef.value);
    if (!m) {
      return null;
    }
    var leading = m[1];
    var comma_groups = m[2] || '';
    var cents = m[3] || '00';
    return Number(leading + comma_groups.replace(/,/g, '') + cents);
  }

  function refreshAmount() {
    var nextAmount = parseCents(amountRef.value);
    if (nextAmount === amount) {
      return;
    }
    if (nextAmount === null) {
      formRef.setAttribute("disabled", "disabled");
      donateButtonRef.setAttribute("disabled", "disabled");
      return;
    } else {
      formRef.removeAttribute("disabled");
      donateButtonRef.removeAttribute("disabled");
    }
    amount = nextAmount;
    paymentRequest.update({
      total: {
        label: 'Mission Bit Donation',
        amount: amount,
      }
    });
  }

  var formRef = document.querySelector('form.donate-form-container');
  var amountRef = document.querySelector("input[name=amount]");
  var donateButtonRef = document.getElementById("donate-button");
  var paymentRequestButtonRef = document.getElementById("payment-request-button");
  var stripe = Stripe(STRIPE_PK);
  var elements = stripe.elements();
  var amount = parseCents(amountRef.value) || parseCents('50');
  var paymentRequest = stripe.paymentRequest({
    country: 'US',
    currency: 'usd',
    total: {
      label: 'Mission Bit Donation',
      amount: amount,
    },
    requestPayerName: true,
    requestPayerEmail: true
  });
  var prButton = elements.create('paymentRequestButton', {
    paymentRequest: paymentRequest,
  });
  paymentRequest.on('token', onToken);
  paymentRequest.on('cancel', onCancel);
  paymentRequest.canMakePayment().then(function (result) {
    if (result) {
      prButton.mount(
        paymentRequestButtonRef,
        {
          style: {
            type: 'donate',
            height: '64px'
          }
        }
      );
    } else {
      paymentRequestButtonRef.style.display = 'none';
    }
  });
  var handler = StripeCheckout.configure({
    key: STRIPE_PK,
    image: 'https://www.missionbit.com/images/icon128.png',
    locale: 'auto',
    panelLabel: 'Donate {{amount}}',
    name: 'Mission Bit',
    description: 'Donate to Mission Bit',
    token: function (token) {
      completeDonation({
        amount: amount,
        token: token.id,
        type: 'checkout'
      }).then(donationCompleted, donationFailed);
    }
  });

  amountRef.addEventListener('change', refreshAmount);
  amountRef.addEventListener('input', refreshAmount);
  donateButtonRef.addEventListener('click', function (e) {
    e.preventDefault();
    if (amount === null) {
      return;
    }
    handler.open({
      amount: amount
    });
  });
  formRef.addEventListener('submit', function (e) {
    e.preventDefault();
    return false;
  });
  refreshAmount();

})();
