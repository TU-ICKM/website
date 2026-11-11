/* ICKM website. Own small script, nothing from other servers, no cookies.
   1. Background videos load shortly before they are visible and pause off screen
      (not with reduced motion or data saving: then the still image stays).
   2. Map journey on the home page: the step in the middle of the screen lights up its cities.
   3. Effects after the model of Motion.dev and Kokonut UI, without a library: cards follow the pointer
      (light spot and slight tilt, springing back), magnetic buttons, numbers that count up,
      bars that grow when they come into view.
   4. Filter on the conference list: cards move to their new place smoothly.
   5. Header that hides when scrolling down and returns when scrolling up, back-to-top button
      (after Aceternity UI and Uiverse, own code).
   Without this script everything is visible and works, only without movement. */
(function () {
  if (!("IntersectionObserver" in window)) return;
  var d = document;
  var mq = function (q) { return window.matchMedia && window.matchMedia(q).matches; };
  var reduce = mq("(prefers-reduced-motion: reduce)");
  var save = navigator.connection && navigator.connection.saveData;
  var fine = mq("(hover: hover) and (pointer: fine)");
  var SPRING = (window.CSS && CSS.supports("transition-timing-function", "linear(0, 1)"))
    ? "linear(0, 0.009, 0.035 2.1%, 0.141, 0.281 6.7%, 0.723 12.9%, 0.938 16.7%, 1.017, 1.077, 1.121, 1.149 24.3%, 1.159, 1.163, 1.161, 1.154 29.9%, 1.129 32.8%, 1.051 39.6%, 1.017 43.1%, 0.991, 0.977 51%, 0.974 53.8%, 0.975 57.1%, 0.997 69.8%, 1.003 76.9%, 1)"
    : "cubic-bezier(0.34, 1.56, 0.64, 1)";
  var each = function (sel, fn) { Array.prototype.forEach.call(d.querySelectorAll(sel), fn); };

  /* 1. Background videos */
  if (!reduce && !save) {
    var vo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var v = e.target;
        if (e.isIntersecting) {
          if (!v.src) v.src = v.dataset.src;
          var p = v.play();
          if (p && p.catch) p.catch(function () {});
        } else if (v.src) {
          v.pause();
        }
      });
    }, { rootMargin: "200px 0px" });
    each("video[data-src]", function (v) { vo.observe(v); });
  }

  /* 2. Map journey */
  var journey = d.querySelector(".journey");
  if (journey) {
    var marks = journey.querySelectorAll(".map [data-y]");
    var steps = journey.querySelectorAll(".step");
    journey.classList.add("live");
    var show = function (step) {
      var upto = +step.dataset.upto;
      var now = (step.dataset.years || "").split(" ");
      Array.prototype.forEach.call(marks, function (m) {
        m.classList.toggle("on", +m.dataset.y <= upto);
        m.classList.toggle("now", now.indexOf(m.dataset.y) > -1);
      });
      Array.prototype.forEach.call(steps, function (s) { s.classList.toggle("active", s === step); });
    };
    var so = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) show(e.target); });
    }, { rootMargin: "-50% 0px -40% 0px" });
    Array.prototype.forEach.call(steps, function (s) { so.observe(s); });
  }

  /* 3a. Cards follow the pointer: light spot and slight tilt, spring back on leave */
  if (fine && !reduce) {
    each(".conf-card a, .link-card, .info-card, .person, .stats li, .tile", function (el) {
      el.classList.add("fx");
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
        el.style.setProperty("--rx", ((0.5 - y) * 5).toFixed(2) + "deg");
        el.style.setProperty("--ry", ((x - 0.5) * 6).toFixed(2) + "deg");
        el.classList.add("fx-on");
      });
      el.addEventListener("pointerleave", function () {
        el.classList.remove("fx-on");
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
      });
    });
    /* 3b. Magnetic buttons */
    each(".magnetic", function (b) {
      b.addEventListener("pointermove", function (e) {
        var r = b.getBoundingClientRect();
        b.style.setProperty("--tx", ((e.clientX - r.left - r.width / 2) * 0.25).toFixed(1) + "px");
        b.style.setProperty("--ty", ((e.clientY - r.top - r.height / 2) * 0.35).toFixed(1) + "px");
      });
      b.addEventListener("pointerleave", function () {
        b.style.setProperty("--tx", "0px");
        b.style.setProperty("--ty", "0px");
      });
    });
  }

  /* 3c. Count up and grow when in view */
  var countUp = function (n) {
    var to = +n.dataset.count;
    if (reduce || !to) { n.textContent = to; return; }
    var t0 = null, dur = 1400;
    n.textContent = "0";
    var step = function (t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / dur);
      n.textContent = p === 1 ? to : Math.round(to * (1 - Math.pow(2, -10 * p)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("is-in");
      io.unobserve(e.target);
      Array.prototype.forEach.call(e.target.querySelectorAll("[data-count]"), countUp);
    });
  }, { threshold: 0.3 });
  each("[data-inview]", function (el) { el.classList.add("pre"); io.observe(el); });

  /* 5. Header floats: glass after the first scroll, hides when you scroll down, comes back when you scroll up.
        The back-to-top button appears further down the page. */
  var hdr = d.querySelector(".site-header"), toTop = d.querySelector(".to-top");
  if (hdr) {
    var lastY = window.scrollY, ticking = false;
    var setHdr = function (hidden) {
      d.documentElement.style.setProperty("--hdr", hidden ? "0px" : hdr.offsetHeight + "px");
    };
    var onScroll = function () {
      ticking = false;
      var y = window.scrollY;
      hdr.classList.toggle("scrolled", y > 8);
      if (Math.abs(y - lastY) > 4) {
        var hide = !d.body.classList.contains("menu-open") && y > lastY && y > hdr.offsetHeight * 2;
        hdr.classList.toggle("hide", hide);
        setHdr(hide);
        lastY = y;
      }
      if (toTop) toTop.classList.toggle("show", y > window.innerHeight * 1.2);
    };
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
    }, { passive: true });
    setHdr(false);
    onScroll();
  }
  if (toTop) {
    toTop.addEventListener("click", function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  }

  /* 4. Filter on the conference list, with smooth layout changes */
  var grid = d.querySelector(".conf-grid"), bar = d.querySelector(".filters");
  if (grid && bar) {
    var cards = Array.prototype.slice.call(grid.children);
    var out = bar.querySelector(".filter-count");
    bar.hidden = false;
    var apply = function (f) {
      var before = new Map();
      cards.forEach(function (c) { if (!c.hidden) before.set(c, c.getBoundingClientRect()); });
      var shown = 0;
      cards.forEach(function (c) {
        var ok = f === "all" || c.dataset.era === f || (f === "proc" && c.dataset.proc === "1");
        c.hidden = !ok;
        if (ok) shown++;
      });
      out.textContent = f === "all" ? "All " + cards.length + " years" : shown + " of " + cards.length + " years";
      if (reduce || !grid.animate) return;
      cards.forEach(function (c) {
        if (c.hidden) return;
        var a = before.get(c), b = c.getBoundingClientRect();
        if (a) {
          var dx = a.left - b.left, dy = a.top - b.top;
          if (dx || dy) c.animate([{ transform: "translate(" + dx + "px," + dy + "px)" }, { transform: "none" }],
                                  { duration: 700, easing: SPRING });
        } else {
          c.animate([{ opacity: 0, transform: "scale(0.92)" }, { opacity: 1, transform: "none" }],
                    { duration: 450, easing: "ease-out" });
        }
      });
    };
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-filter]");
      if (!b) return;
      Array.prototype.forEach.call(bar.querySelectorAll("button[data-filter]"), function (x) {
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      });
      apply(b.dataset.filter);
    });
    out.textContent = "All " + cards.length + " years";
  }
})();
