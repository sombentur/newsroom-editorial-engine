// After an extension update Chrome detaches the content script from pages opened earlier; messages
// then fail with "Receiving end does not exist". Re-inject it (or reload the page, which keeps the
// Gemini/ChatGPT conversation) instead of stopping the job.
export const isMissingObserver = e => /Receiving end does not exist|Could not establish connection/i.test(String(e?.message ?? e));

export async function reconnectObserver(chrome, tabId) {
  try {
    if (chrome.scripting?.executeScript) {
      await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
      return 'injected';
    }
  } catch {}
  await chrome.tabs.reload(tabId);
  return 'reloaded';
}

// A page message or browser command that never answers (e.g. a screenshot of a background tab, which
// Chrome does not paint) must fail after a while instead of freezing every job in the extension.
export function withTimeout(promise, ms, label) {
  let timer;
  const limit = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(label + ' timed out')), ms); });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
}
