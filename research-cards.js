(() => {
  "use strict";

  const container = document.querySelector(
    ".research-overview-grid-composed"
  );

  if (!container) return;

  const cards = Array.from(
    container.querySelectorAll(".research-feature-card")
  );

  function closeCard(card, restoreFocus = true) {
    if (!card || !card.classList.contains("is-expanded")) return;

    const openButton = card.querySelector(
      ".research-feature-open"
    );

    const detail = card.querySelector(
      ".research-feature-detail"
    );

    card.classList.remove("is-expanded");

    openButton?.setAttribute(
      "aria-expanded",
      "false"
    );

    if (detail) {
      detail.hidden = true;
    }

    if (restoreFocus) {
      openButton?.focus();
    }
  }

  function openCard(card) {
    cards.forEach((otherCard) => {
      if (otherCard !== card) {
        closeCard(otherCard, false);
      }
    });

    const openButton = card.querySelector(
      ".research-feature-open"
    );

    const detail = card.querySelector(
      ".research-feature-detail"
    );

    const closeButton = card.querySelector(
      ".research-feature-close"
    );

    card.classList.add("is-expanded");

    openButton?.setAttribute(
      "aria-expanded",
      "true"
    );

    if (detail) {
      detail.hidden = false;
    }

    requestAnimationFrame(() => {
      closeButton?.focus();
    });
  }

  cards.forEach((card) => {
    const openButton = card.querySelector(
      ".research-feature-open"
    );

    const closeButton = card.querySelector(
      ".research-feature-close"
    );

    openButton?.addEventListener("click", () => {
      openCard(card);
    });

    closeButton?.addEventListener("click", () => {
      closeCard(card);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;

    const expandedCard = container.querySelector(
      ".research-feature-card.is-expanded"
    );

    if (expandedCard) {
      closeCard(expandedCard);
    }
  });
})();
