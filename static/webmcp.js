/* WebMCP tools for vpsdealswire.com homepage.
 *
 * Exposes the page's real deal-filter as agent tools via the WebMCP API
 * (document.modelContext, falling back to navigator.modelContext).
 * Feature-detected: if the API is unavailable this script is a no-op and
 * the page works exactly as before. Tools only read/filter the deals that
 * are already rendered on the page — no invented data, no side effects.
 */
(function () {
  "use strict";

  function modelContext() {
    try {
      if (document.modelContext && typeof document.modelContext.registerTool === "function") {
        return document.modelContext;
      }
      if (navigator.modelContext && typeof navigator.modelContext.registerTool === "function") {
        return navigator.modelContext;
      }
    } catch (e) { /* no-op */ }
    return null;
  }

  var mc = modelContext();
  if (!mc) return;

  function textOf(el) {
    return el ? (el.textContent || "").trim() : "";
  }

  // Deals currently visible after the page's own filter runs.
  function visibleDeals() {
    var out = [];
    var cards = document.querySelectorAll("#deal-list .deal-card");
    for (var i = 0; i < cards.length; i++) {
      var a = cards[i];
      if (a.style.display === "none") continue;
      var priceAttr = a.getAttribute("data-price");
      out.push({
        title: textOf(a.querySelector(".title")),
        price: textOf(a.querySelector(".price")),
        price_usd: priceAttr === null ? null : parseFloat(priceAttr),
        provider: a.getAttribute("data-provider"),
        url: a.href,
      });
    }
    return out;
  }

  // Drive the page's real filter UI (same code path as a human typing).
  function applyFilter(maxPrice, provider) {
    var maxEl = document.getElementById("f-maxprice");
    var provEl = document.getElementById("f-provider");
    if (maxEl) {
      maxEl.value = maxPrice === undefined || maxPrice === null ? "" : String(maxPrice);
      maxEl.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (provEl && provider !== undefined) {
      provEl.value = provider || "";
      provEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  var controller = new AbortController();
  var opts = { signal: controller.signal };

  function register(tool) {
    try {
      var p = mc.registerTool(tool, opts);
      if (p && typeof p.catch === "function") p.catch(function () {});
    } catch (e) { /* scanner or browser without support */ }
  }

  register({
    name: "search_deals",
    description:
      "Filter the live VPS deal list on this page by maximum monthly USD price " +
      "and/or provider slug, then return the matching deals as structured data.",
    inputSchema: {
      type: "object",
      properties: {
        max_price_usd: { type: "number", description: "Maximum monthly price in USD" },
        provider: { type: "string", description: "Provider slug, e.g. digitalocean" },
      },
      additionalProperties: false,
    },
    execute: function (args) {
      args = args || {};
      applyFilter(args.max_price_usd, args.provider);
      var deals = visibleDeals().slice(0, 25);
      return Promise.resolve({ count: deals.length, deals: deals });
    },
  });

  register({
    name: "get_visible_deals",
    description:
      "Return the VPS deals currently visible on the page as structured data " +
      "(title, price, provider slug, URL).",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Max deals to return", default: 25 },
      },
      additionalProperties: false,
    },
    execute: function (args) {
      var limit = Math.min((args && args.limit) || 25, 50);
      var deals = visibleDeals().slice(0, limit);
      return Promise.resolve({ count: deals.length, deals: deals });
    },
  });
})();
