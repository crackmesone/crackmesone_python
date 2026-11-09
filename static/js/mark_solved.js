/**
 * mark_solved.js -- Issue #182: Manual "Mark as Done"
 *
 * Responsibilities:
 *   1. On DOMContentLoaded: reorder <tbody> so .crackme-row-solved rows
 *      sink to the bottom (CSS `order` doesn't work on <tr>).
 *   2. Handle toggle button clicks via event delegation (single listener).
 *   3. POST to /crackme/<hexid>/toggle-manual-solve with CSRF.
 *   4. Optimistic UI update: change state immediately, roll back on error.
 *   5. Guest fallback: if not logged in, use localStorage only.
 *
 * NOTE (pagination): Row reordering is per-page (client-side DOM only).
 * A user may see solved rows at the bottom of page 1 and unsolved rows at
 * the top of page 2. This is expected for a purely client-side sort.
 * Server-side hide_solved=1 fully excludes solved rows at query level.
 *
 * No external dependencies. No jQuery. No ES modules.
 */
(function () {
  'use strict';

  // -- Constants ---------------------------------------------------------------
  var SOLVED_CLASS   = 'crackme-row-solved';
  var GLYPH_UNSOLVED = '\u2610'; // ☐
  var GLYPH_SOLVED   = '\u2611'; // ☑
  var LS_KEY         = 'crackmesone_manual_solved';

  // -- localStorage fallback (guests / localStorage blocked) ------------------
  function lsLoad() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch (e) { return new Set(); }
  }

  function lsSave(set) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(Array.from(set))); }
    catch (e) { /* quota exceeded or blocked -- silent no-op */ }
  }

  // -- DOM helpers -------------------------------------------------------------
  function applyState(row, btn, isSolved) {
    if (isSolved) {
      row.classList.add(SOLVED_CLASS);
      btn.textContent  = GLYPH_SOLVED;
      btn.title        = 'Mark as undone';
      btn.setAttribute('aria-label', 'Mark as undone');
    } else {
      row.classList.remove(SOLVED_CLASS);
      btn.textContent  = GLYPH_UNSOLVED;
      btn.title        = 'Mark as done';
      btn.setAttribute('aria-label', 'Mark as done');
    }
  }

  /**
   * Reorder rows: move all solved rows to the bottom of tbody, preserving
   * their relative order. Uses appendChild (move, not clone).
   * Called once at init and once per toggle.
   */
  function reorderRows(tbody) {
    var solved = Array.prototype.filter.call(
      tbody.querySelectorAll('tr.' + SOLVED_CLASS),
      function (r) { return r.classList.contains(SOLVED_CLASS); }
    );
    solved.forEach(function (row) { tbody.appendChild(row); });
  }

  // -- Hide-solved checkbox: instant client-side toggle -----------------------
  function wireHideSolvedCheckbox(tbody) {
    var chk = document.getElementById('hide-solved-checkbox');
    if (!chk) return;

    function updateCrackyLink() {
      var crackyBtn = document.getElementById('btn-random-cracky');
      if (crackyBtn) {
        try {
          var url = new URL(crackyBtn.href, window.location.origin);
          if (chk.checked) {
            url.searchParams.set('hide_solved', '1');
          } else {
            url.searchParams.delete('hide_solved');
          }
          crackyBtn.href = url.pathname + url.search;
        } catch (e) {}
      }
    }

    chk.addEventListener('change', function () {
      var hide = chk.checked;
      updateCrackyLink();
      if (tbody) {
        Array.prototype.forEach.call(
          tbody.querySelectorAll('tr.' + SOLVED_CLASS),
          function (row) { row.style.display = hide ? 'none' : ''; }
        );
      }
    });

    updateCrackyLink();

    // Apply on load in case the checkbox starts checked but rows are present
    if (chk.checked && tbody) {
      Array.prototype.forEach.call(
        tbody.querySelectorAll('tr.' + SOLVED_CLASS),
        function (row) { row.style.display = 'none'; }
      );
    }
  }

  // -- Challenge viewing page handler (Issue #182) ----------------------------
  function wireSingleChallengePage(isLoggedIn) {
    var btn = document.getElementById('page-mark-solved-btn');
    if (!btn) return;

    var hexid = btn.getAttribute('data-crackme-id');
    if (!hexid) return;

    var statusSpan = document.getElementById('page-progress-status');

    function updateSingleUI(isSolved) {
      var iconSpan  = btn.querySelector('.mark-icon');
      var labelSpan = btn.querySelector('.mark-label');
      var glyph = isSolved ? GLYPH_SOLVED : GLYPH_UNSOLVED;

      if (iconSpan)  iconSpan.textContent  = glyph;
      if (labelSpan) labelSpan.textContent = isSolved ? 'Done' : 'Mark as done';
      btn.title = isSolved ? 'Mark it as undone. Only visible to yourself' : 'Mark as done. Only visible to yourself';
      btn.setAttribute('aria-label', isSolved ? 'Mark as undone' : 'Mark as done');

      if (isSolved) {
        btn.classList.add('is-solved');
        btn.classList.add('active');
      } else {
        btn.classList.remove('is-solved');
        btn.classList.remove('active');
      }

      if (statusSpan) {
        statusSpan.className = isSolved ? 'text-success' : 'text-gray';
        var statusIcon = statusSpan.querySelector('.mark-icon');
        var statusText = statusSpan.querySelector('.mark-text');
        if (statusIcon) statusIcon.textContent = glyph;
        if (statusText) statusText.textContent = isSolved ? 'Marked as done' : 'Not done yet';
      }
    }

    if (statusSpan) {
      statusSpan.addEventListener('click', function (e) {
        if (e.target.tagName === 'A') return;
        btn.click();
      });
    }

    // Guest: apply localStorage state if logged out
    if (!isLoggedIn) {
      var stored = lsLoad();
      if (stored.has(hexid)) {
        updateSingleUI(true);
      }
    }

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var wasSolved = btn.classList.contains('active') || btn.classList.contains('is-solved');
      var nextSolved = !wasSolved;

      // Optimistic update
      updateSingleUI(nextSolved);

      if (!isLoggedIn) {
        var guestStored = lsLoad();
        nextSolved ? guestStored.add(hexid) : guestStored.delete(hexid);
        lsSave(guestStored);
        return;
      }

      btn.disabled = true;
      postToggle(hexid, function (err, data) {
        btn.disabled = false;
        if (err || !data || !data.ok) {
          // Rollback on failure
          updateSingleUI(wasSolved);
          var msg = (data && data.error) ? data.error : 'Network error. Please try again.';
          console.error('[mark_solved] Single toggle failed:', msg);
          alert('⚠️ ' + msg);
        }
      });
    });
  }

  // -- API call ----------------------------------------------------------------
  function postToggle(hexid, callback) {
    var csrf = (typeof window.CSRF_TOKEN !== 'undefined') ? window.CSRF_TOKEN : '';
    fetch('/crackme/' + hexid + '/toggle-manual-solve', {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrf,
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
    })
    .then(function (resp) { return resp.json(); })
    .then(function (data) { callback(null, data); })
    .catch(function (err) { callback(err, null); });
  }

  // -- Main init ---------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function () {
    var isLoggedIn = (typeof window.IS_LOGGED_IN !== 'undefined')
                   ? window.IS_LOGGED_IN
                   : false;

    // 1. Single challenge viewing page
    wireSingleChallengePage(isLoggedIn);

    // 2. List pages (search results / latest)
    var tbody = document.getElementById('search-results')
             || document.getElementById('content-list');
    if (!tbody) return; // Not a list page

    // For guests: apply localStorage state to any rows the server rendered
    // as unsolved (they won't have the solved class yet)
    if (!isLoggedIn) {
      var stored = lsLoad();
      Array.prototype.forEach.call(
        tbody.querySelectorAll('tr.crackme-row[data-crackme-id]'),
        function (row) {
          var hexid = row.getAttribute('data-crackme-id');
          var btn   = row.querySelector('.btn-mark-solved[data-crackme-id]');
          if (!btn) return;
          if (stored.has(hexid)) applyState(row, btn, true);
        }
      );
    }

    // Initial reorder: push solved rows to the bottom
    reorderRows(tbody);

    // Wire hide-solved checkbox for instant client feedback
    wireHideSolvedCheckbox(tbody);

    // -- Event delegation: single listener on <tbody> -------------------------
    tbody.addEventListener('click', function (e) {
      var btn = e.target.closest('.btn-mark-solved');
      if (!btn) return;

      var hexid = btn.getAttribute('data-crackme-id');
      if (!hexid) return;

      var row = btn.closest('tr.crackme-row');
      if (!row) return;

      var wasAlreadySolved = row.classList.contains(SOLVED_CLASS);
      var nextSolved       = !wasAlreadySolved;

      // -- Optimistic update (instant feedback) -------------------------------
      applyState(row, btn, nextSolved);

      // Re-sort: move row to its correct zone immediately
      if (nextSolved) {
        tbody.appendChild(row); // sink to bottom
      } else {
        // Rise: insert before the first currently-solved row
        var firstSolved = tbody.querySelector('tr.' + SOLVED_CLASS);
        if (firstSolved && firstSolved !== row) {
          tbody.insertBefore(row, firstSolved);
        }
      }

      // -- Hide-solved checkbox: hide the row if checkbox is active ----------
      var chk = document.getElementById('hide-solved-checkbox');
      if (nextSolved && chk && chk.checked) {
        row.style.display = 'none';
      } else {
        row.style.display = '';
      }

      if (!isLoggedIn) {
        // Guest: persist to localStorage only
        var guestStored = lsLoad();
        nextSolved ? guestStored.add(hexid) : guestStored.delete(hexid);
        lsSave(guestStored);
        return;
      }

      // -- Authenticated: sync to server ------------------------------------
      btn.disabled = true; // prevent double-click during flight

      postToggle(hexid, function (err, data) {
        btn.disabled = false;

        if (err || !data || !data.ok) {
          // -- Rollback on failure --------------------------------------------
          applyState(row, btn, wasAlreadySolved);

          // Re-sort back
          if (wasAlreadySolved) {
            tbody.appendChild(row);
          } else {
            var firstS = tbody.querySelector('tr.' + SOLVED_CLASS);
            if (firstS && firstS !== row) tbody.insertBefore(row, firstS);
          }

          // Restore hide-state
          if (wasAlreadySolved && chk && chk.checked) {
            row.style.display = 'none';
          } else {
            row.style.display = '';
          }

          var msg = (data && data.error) ? data.error : 'Network error. Please try again.';
          console.error('[mark_solved] Toggle failed:', msg);

          // Insert a dismissible notice above the table (no alert())
          var notice = document.createElement('p');
          notice.style.cssText = 'color:#e74c3c;font-size:0.85rem;margin:4px 0;';
          notice.textContent   = '\u26a0\ufe0f ' + msg;
          var table = tbody.closest('.table-responsive') || tbody.parentElement;
          if (table && table.parentElement) {
            table.parentElement.insertBefore(notice, table);
            setTimeout(function () { notice.remove(); }, 4000);
          }
        }
        // On success: the optimistic update is already applied, nothing to do.
      });
    });
  });

})();
