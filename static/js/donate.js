"use strict";

(function () {

  function donationItem(amount, frequency) {
    return {
      id: frequency === 'monthly' ? 'web-donation-monthly' : 'web-donation-once',
      name: frequency === 'monthly' ? 'Monthly Donation' : 'One-time Donation',
      price: amount / 100,
      quantity: 1
    };
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

  function parseFrequency(s) {
    return s === 'monthly' ? 'monthly' : 'once';
  }

  function refreshFrequency() {
    Array.prototype.forEach.call(frequencyRefs, function (frequencyRef) {
      if (frequencyRef.checked) {
        frequency = parseFrequency(frequencyRef.value);
      }
    });
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

  /*
  iOS Safari viewport action bar workaround.

    See also:
    * https://www.eventbrite.com/engineering/mobile-safari-why/
    * https://nicolas-hoizey.com/2015/02/viewport-height-is-taller-than-the-visible-part-of-the-document-in-some-mobile-browsers.html
    * https://medium.com/samsung-internet-dev/toolbars-keyboards-and-the-viewports-10abcc6c3769
  */
  function checkOrientation() {
    console.log({ innerHeight: window.innerHeight, scrollHeight: containerRef.scrollHeight });
    if (window.innerHeight < containerRef.scrollHeight) {
      containerRef.style.maxHeight = window.innerHeight + 'px';
    } else if (containerRef.style.maxHeight) {
      containerRef.style.maxHeight = "";
    }
  }
  function onResizeAfterOrientationChange(e) {
    window.removeEventListener('resize', onResizeAfterOrientationChange);
    checkOrientation();
  }

  function trackCheckoutEvent(paymentMethod) {
    var item = donationItem(amount, frequency);
    gtag('event', 'begin_checkout', {
      items: [item],
      coupon: ""
    });
    gtag('event', 'set_checkout_option', {
      checkout_step: 1,
      checkout_option: 'payment method',
      value: paymentMethod
    });
    fbq('track', 'InitiateCheckout', {
      value: item.price,
      currency: 'USD',
      contents: [{
        id: item.id,
        quantity: item.quantity,
        item_price: item.price
      }],
      content_ids: [item.id],
      content_type: 'product',
      payment_method: paymentMethod
    });
  }

  var containerRef = document.querySelector('.container');
  var formRef = document.querySelector('form.donate-form-container');
  var amountRef = document.querySelector("input[name=amount]");
  var frequencyRefs = document.querySelectorAll("input[name=frequency]");
  var donateButtonRef = document.getElementById("donate-button");
  var errorRef = document.querySelector('.donate-form-body .error');
  var checkLinkRef = document.querySelector('#give-by-check-link');
  var checkModalRef = document.querySelector('#give-by-check');
  var modalCloseRef = document.querySelector('.modal-close');
  var stripe = Stripe(window.STRIPE_PK);
  var amount = parseCents(amountRef.value) || parseCents('50');
  var frequency = 'once';
  refreshFrequency();

  Array.prototype.forEach.call(frequencyRefs, function (frequencyRef) {
    frequencyRef.addEventListener('change', refreshFrequency);
  });
  amountRef.addEventListener('change', refreshAmount);
  amountRef.addEventListener('input', refreshAmount);
  donateButtonRef.addEventListener('click', function (e) {
    e.preventDefault();
    if (amount === null) {
      return;
    }
    trackCheckoutEvent('Stripe Checkout');
    fetch('/checkout', {
      method: 'POST',
      body: JSON.stringify({
        amount: amount,
        frequency: frequency,
        metadata: window.METADATA
      }),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    }).then(function (response) {
      if (response.ok) {
        return response.json();
      } else {
        throw new Error("Could not connect to server, please try again.");
      }
    }).then(function (response) {
      return stripe.redirectToCheckout(response).then(function (result) {
        throw new Error(result.error.message);
      });
    }).catch(donationFailed);
  });
  checkLinkRef.addEventListener('click', function (e) {
    e.preventDefault();
    showCheckInstructions();
  });
  checkModalRef.addEventListener('click', function (e) {
    // Only register clicks that fall outside of the modal's content
    if (e.target === e.currentTarget) {
      e.preventDefault();
      hideCheckInstructions();
    }
  });
  modalCloseRef.addEventListener('click', function (e) {
    e.preventDefault();
    hideCheckInstructions();
  });
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
  window.addEventListener('orientationchange', function (_e) {
    window.addEventListener('resize', onResizeAfterOrientationChange);
  });
  checkOrientation();


})();
