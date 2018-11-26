"use strict";

(function () {
  function onToken(e) {
    console.log(e);
    completeDonation({
      token: e.token,
      email: e.payerEmail,
      name: e.payerName,
      type: 'paymentRequest',
      amount: amount,
      metadata: METADATA
    }).then(
      function (result) {
        e.complete('success');
        donationCompleted(result);
      },
      function (err) {
        e.complete('fail');
        donationFailed(err);
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

  function oneTimeDonationItems(amount) {
    return [{
      id: 'web-donation-once',
      name: 'One-time Donation',
      price: amount / 100,
      quantity: 1
    }];
  }

  function donationCompleted(result) {
    console.log({ donationCompleted: result });
    gtag('event', 'purchase', {
      transaction_id: result.id,
      value: result.amount / 100,
      currency: 'USD',
      tax: 0,
      shipping: 0,
      items: oneTimeDonationItems(result.amount)
    });
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

  function onKeyDownCheckModal(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      hideCheckInstructions();
    }
  }

  function showCheckInstructions() {
    checkModalRef.classList.add('open');
    window.addEventListener('keydown', onKeyDownCheckModal);
    window.location.hash = '#give-by-check';
  }

  function hideCheckInstructions() {
    checkModalRef.classList.remove('open');
    window.removeEventListener('keydown', onKeyDownCheckModal);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(
        null,
        document.title,
        window.location.pathname + window.location.search
      );
    } else {
      window.location.hash = '';
    }
  }

  function onClickCloseCheckInstructions(e) {
    e.preventDefault();
    hideCheckInstructions();
  }

  var formRef = document.querySelector('form.donate-form-container');
  var amountRef = document.querySelector("input[name=amount]");
  var donateButtonRef = document.getElementById("donate-button");
  var paymentRequestButtonRef = document.getElementById("payment-request-button");
  var errorRef = document.querySelector('.donate-form-body .error');
  var checkLinkRef = document.querySelector('#give-by-check-link');
  var checkModalRef = document.querySelector('#give-by-check');
  var modalCloseRef = document.querySelector('.modal-close');
  var stripe = Stripe(STRIPE_PK);
  var elements = stripe.elements();
  var amount = parseCents(amountRef.value) || parseCents('50');
  var applePay = false;
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
      applePay = result.applePay;
      prButton.mount(paymentRequestButtonRef);
      formRef.classList.add('payment-request');
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
        email: token.email,
        name: token.card.name,
        type: 'checkout',
        metadata: METADATA
      }).then(donationCompleted, donationFailed);
    }
  });

  amountRef.addEventListener('change', refreshAmount);
  amountRef.addEventListener('input', refreshAmount);
  prButton.on('click', function () {
    gtag('event', 'begin_checkout', {
      items: oneTimeDonationItems(amount),
      coupon: ""
    });
    gtag('event', 'set_checkout_option', {
      checkout_step: 1,
      checkout_option: 'payment method',
      value: applePay ? 'Apple Pay' : 'Payment Request'
    });
  });
  donateButtonRef.addEventListener('click', function (e) {
    e.preventDefault();
    if (amount === null) {
      return;
    }
    gtag('event', 'begin_checkout', {
      items: oneTimeDonationItems(amount),
      coupon: ""
    });
    gtag('event', 'set_checkout_option', {
      checkout_step: 1,
      checkout_option: 'payment method',
      value: 'Stripe Checkout'
    });
    handler.open({
      amount: amount
    });
  });
  checkLinkRef.addEventListener('click', function (e) {
    e.preventDefault();
    showCheckInstructions();
  });
  checkModalRef.addEventListener('click', onClickCloseCheckInstructions);
  modalCloseRef.addEventListener('click', onClickCloseCheckInstructions);
  formRef.addEventListener('submit', function (e) {
    e.preventDefault();
    return false;
  });
  if (window.location.hash === '#give-by-check') {
    showCheckInstructions();
  }
  refreshAmount();
  if (window.performance) {
    // Gets the number of milliseconds since page load
    // (and rounds the result since the value must be an integer).
    var timeSincePageLoad = Math.round(performance.now());

    // Sends the timing event to Google Analytics.
    gtag('event', 'timing_complete', {
      'name': 'load',
      'value': timeSincePageLoad,
      'event_category': 'JS Dependencies'
    });
  }
})();
