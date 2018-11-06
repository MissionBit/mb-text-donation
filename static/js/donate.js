"use strict";

(function () {
  var stripe = Stripe(STRIPE_PK);
  var elements = stripe.elements();
  var lastAmount = null;
  var paymentRequest = null;
  var prButton = null;
  var formRef = document.querySelector('form.donate-form-container');
  var amountRef = document.querySelector("input[name=amount]");
  var donateButtonRef = document.getElementById("donate-button");
  var paymentRequestButtonRef = document.getElementById("payment-request-button");
  var DOLLAR_RE = /^\s*\$?([1-9]\d*)((?:,\d\d\d)*)(?:\.(\d\d))?\s*$/;
  var handler = StripeCheckout.configure({
    key: STRIPE_PK,
    image: 'https://www.missionbit.com/images/icon128.png',
    locale: 'auto',
    panelLabel: 'Donate {{amount}}',
    name: 'Mission Bit',
    description: 'Donate to Mission Bit',
    token: function (token) {
      completeDonation({
        amount: lastAmount,
        token: token.id,
        type: 'checkout'
      }).then(donationCompleted, donationFailed);
    }
  });

  function donationCompleted() {
    console.log('completed');
  }

  function donationFailed() {
    console.log('failed');
  }

  function completeDonation(opts) {
    console.log(opts);
    return new Promise.reject(new Error('Not Implemented'));
  }
  
  function parseCents(s) {
    var m = DOLLAR_RE.exec(amountRef.value);
    if (!m) {
      return null;
    }
    var leading = m[1];
    var comma_groups = m[2] || '';
    var cents = m[3] || '00';
    return Number(leading + comma_groups.replace(/,/g, '') + cents);
  }

  function refreshAmount() {
    var amount = parseCents(amountRef.value);
    if (amount === lastAmount) {
      return;
    }
    lastAmount = amount;
    paymentRequest = stripe.paymentRequest({
      country: 'US',
      currency: 'usd',
      total: {
        label: 'Mission Bit Donation',
        amount: amount,
      },
      requestPayerName: true,
      requestPayerEmail: true
    });
    prButton = elements.create('paymentRequestButton', {
      paymentRequest: paymentRequest,
    });

    function onToken(e) {
      console.log(e);
      completeDonation({
        token: e.token.id,
        type: 'paymentRequest',
        amount: lastAmount
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
  }

  amountRef.addEventListener('change', refreshAmount);
  donateButtonRef.addEventListener('click', function (e) {
    e.preventDefault();
    if (lastAmount === null) {
      return;
    }
    handler.open({
      name: null,
      amount: lastAmount
    });
  });
  formRef.addEventListener('submit', function (e) {
    e.preventDefault();
  });
  refreshAmount();
  
})();
