/* Config deck/source pruning after removing a deck row. */
const ChoiceConfigDeck = (function () {
  function pruneAfterDeckRemoval(cfg, deckId) {
    const removed = (cfg.decks || []).find((d) => d.id === deckId);
    const decks = (cfg.decks || []).filter((d) => d.id !== deckId);
    const sources = (cfg.sources || []).filter((s) => {
      if (!removed || s.id !== removed.source) return true;
      return decks.some((d) => d.source === s.id);
    });
    return { decks, sources, removed };
  }

  return { pruneAfterDeckRemoval };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceConfigDeck = ChoiceConfigDeck;
}
