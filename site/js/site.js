// Site-wide helpers for the static rebuild.

// Home valuation: the original step 1 waits for Google Maps (keyed by Luxury Presence) and only
// unlocks "Continue" after a Places pick. With no Maps key here, give it a tiny stand-in so the
// form works: any address that starts with a house number counts as valid; the map stays hidden.
document.addEventListener('DOMContentLoaded', function () {
  if (!document.getElementById('home-valuation-map')) return;
  var style = document.createElement('style');
  style.textContent = '#home-valuation-map{display:none!important}';
  document.head.appendChild(style);
  function noop() {}
  function Autocomplete(input) {
    var listeners = [], timer, self = this;
    this.getPlace = function () {
      var ok = /^\s*\d+\s+\S+/.test(input.value);
      return { address_components: ok ? [{ types: ['street_number'] }] : [], geometry: ok ? { location: {} } : null };
    };
    this.addListener = function (ev, fn) { if (ev === 'place_changed') listeners.push(fn); };
    input.addEventListener('keyup', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { listeners.forEach(function (fn) { fn.call(self); }); }, 600);
    });
  }
  function Map() { this.panTo = noop; this.setZoom = noop; this.setCenter = noop; }
  function Marker() { this.setPosition = noop; this.addListener = noop; }
  function Geocoder() { this.geocode = function (req, cb) { cb([], 'ZERO_RESULTS'); }; }
  window.google = window.google || { maps: {
    Map: Map, Marker: Marker, Geocoder: Geocoder, GeocoderStatus: { OK: 'OK' },
    places: { Autocomplete: Autocomplete }, event: { trigger: noop, clearListeners: noop }
  } };
  var lp = window.luxuryPresence;
  if (lp && lp.mapApiLoader) lp.mapApiLoader.load = function () { return Promise.resolve(); };
  if (lp && lp.redirects) lp.redirects.checkHstRedirect = function () { return false; };
});

// API replay: the original page scripts ask Luxury Presence's servers for testimonials, featured
// properties, and session info. Those answers were recorded at migration time into
// /data/api.json, and are served from there so the pages render the same with no backend.
(function () {
  var PATHS = /^\/(graphql|api-nv\/graphql|api-gw\/graphql|api-l\/geo|api\/v1\/map)$/;
  var recorded = null;
  function load() {
    if (!recorded) {
      recorded = origFetch.call(window, '/data/api.json').then(function (r) { return r.json(); })
        .catch(function () { return []; });
    }
    return recorded;
  }
  function opOf(body) {
    if (!body) return '';
    try {
      var q = JSON.parse(body).query || '';
      var m = q.match(/query\s+(\w+)/);
      return m ? m[1] : 'anonymous';
    } catch (e) { return ''; }
  }
  function lookup(path, body) {
    // The live map-key endpoint answers with an empty body, so the map stays off; do the same.
    if (path === '/api/v1/map') return Promise.resolve({ ct: 'text/html', body: '' });
    var op = opOf(body);
    var page = location.pathname.replace(/\/$/, '') || '/';
    return load().then(function (list) {
      var hits = list.filter(function (r) { return r.path === path && r.op === op; });
      var hit = hits.filter(function (r) { return r.page === page; })[0] || hits[0];
      return hit ? { ct: hit.ct, body: hit.body } : { ct: 'application/json', body: '{"data":null}' };
    });
  }
  function match(url) {
    try {
      var u = new URL(url, location.href);
      return u.origin === location.origin && PATHS.test(u.pathname) ? u.pathname : null;
    } catch (e) { return null; }
  }

  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url);
    var path = match(url);
    if (!path) return origFetch.apply(window, arguments);
    var body = init && typeof init.body === 'string' ? init.body : '';
    return lookup(path, body).then(function (r) {
      return new Response(r.body, { status: 200, headers: { 'Content-Type': r.ct || 'application/json' } });
    });
  };

  var open = XMLHttpRequest.prototype.open;
  var send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__replay = match(url);
    return open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (!this.__replay) return send.apply(this, arguments);
    var xhr = this;
    lookup(this.__replay, typeof body === 'string' ? body : '').then(function (r) {
      var props = { readyState: 4, status: 200, statusText: 'OK', responseText: r.body,
        response: xhr.responseType === 'json' ? JSON.parse(r.body) : r.body, responseURL: location.origin + xhr.__replay };
      Object.keys(props).forEach(function (k) { Object.defineProperty(xhr, k, { value: props[k], configurable: true }); });
      xhr.getResponseHeader = function (h) { return /content-type/i.test(h) ? (r.ct || 'application/json') : null; };
      xhr.getAllResponseHeaders = function () { return 'content-type: ' + (r.ct || 'application/json') + '\r\n'; };
      ['readystatechange', 'load', 'loadend'].forEach(function (t) {
        xhr.dispatchEvent(new Event(t)); // also runs xhr.on<type> handlers
      });
    });
  };
})();
// Forms: Luxury Presence's script sends leads to its own API, reached both from the submit event
// and from buttons that call contactForms.submitForm() directly. Rather than intercept each
// path, swap out its one network step (_submitLeadRequest) so the same fields go to Netlify
// Forms. Everything else (validation, honeypot, success and error states) stays the original.
document.addEventListener('DOMContentLoaded', function () {
  var cf = window.luxuryPresence && window.luxuryPresence.contactForms;
  if (!cf) return;
  var lastForm = null;
  var build = cf._buildSubmissionData;
  cf._buildSubmissionData = function (values, fields, form) {
    lastForm = form;
    return build.apply(this, arguments);
  };
  cf._submitLeadRequest = function () {
    var form = lastForm;
    var params = new URLSearchParams();
    new FormData(form).forEach(function (v, k) { if (typeof v === 'string') params.append(k, v); });
    return fetch('/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString()
    }).then(function (r) {
      if (!r.ok) {
        var err = new Error('HTTP ' + r.status);
        err.userMessage = 'Something went wrong. Please try again, or email lj@ljresidentialgroup.com.';
        throw err;
      }
      return {};
    });
  };
});
