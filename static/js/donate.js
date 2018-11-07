"use strict";

(function () {
  function onToken(e) {
    console.log(e);
    completeDonation({
      token: e.token,
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

  function forEach(arrayLike, f) {
    Array.prototype.forEach.call(arrayLike, f);
  }

  function spanReplace(parent, selector, text) {
    forEach(parent.querySelectorAll(selector), function (el) {
      el.innerText = text;
    });
  }

  function donationCompleted(result) {
    console.log({ donationCompleted: result });
    formRef.classList.add('success');
    formRef.classList.toggle('email-sent', result.email_sent);
    spanReplace(formRef, '.donor-email', result.email);
    spanReplace(formRef, '.donor-transaction-id', result.id);
    forEach(formRef.querySelectorAll('a.donate-email-link'), function (el) {
      el.href = el.href.replace(/\S+$/, result.id);
    });
  }

  function donationFailed(err) {
    console.log({ donationFailed: err });
    errorRef.innerText = "Donation failed, you have not been charged.";
    amountRef.removeAttribute("disabled");
    if (!formRef.classList.contains('invalid')) {
      formRef.removeAttribute("disabled");
      donateButtonRef.removeAttribute("disabled");
    }
  }

  function completeDonation(opts) {
    console.log({ completeDonation: opts });
    errorRef.innerText = "";
    formRef.classList.add('processing');
    formRef.setAttribute("disabled", "disabled");
    donateButtonRef.setAttribute("disabled", "disabled");
    amountRef.setAttribute("disabled", "disabled");

    return fetch('/charge', {
      method: 'POST',
      body: JSON.stringify(opts),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }).then(function (response) {
      if (response.ok) {
        return response.json();
      } else {
        throw new Error("Payment attempt failed");
      }
    }).finally(function () {
      formRef.classList.remove('processing');
    });
  }

  function parseCents(s) {
    /* Parse a string representing a dollar value to cents */

    var m = /^\s*\$?([1-9]\d*)((?:,\d\d\d)*)(?:\.(\d\d))?\s*$/.exec(s);
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
      formRef.classList.add('invalid');
      formRef.setAttribute("disabled", "disabled");
      donateButtonRef.setAttribute("disabled", "disabled");
      return;
    } else {
      formRef.classList.remove('invalid');
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
  var errorRef = document.querySelector('.donate-form-body .error');
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
    style: {
      paymentRequestButton: {
        type: 'donate',
        height: '64px'
      }
    }
  });
  paymentRequest.on('token', onToken);
  paymentRequest.on('cancel', onCancel);
  paymentRequest.canMakePayment().then(function (result) {
    if (result) {
      prButton.mount(paymentRequestButtonRef);
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
      console.log({ handlerToken: token });
      completeDonation({
        amount: amount,
        token: token,
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
