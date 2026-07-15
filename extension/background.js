/**
 * Background service worker for Matrix Bridge extension.
 */

console.log("Matrix Bridge: Background service worker loaded");

const API_URL = "http://localhost:8000";

// Listen for tab updates
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete") {
    // Check if it's a Claude or ChatGPT tab
    if (tab.url?.includes("claude.ai") || tab.url?.includes("chat.openai.com")) {
      console.log("Matrix Bridge: Active tab detected", tab.url);
    }
  }
});

// Handle sync requests
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "sync") {
    performSync(request.data).then(result => {
      sendResponse({ success: true, result });
    });
    return true; // Keep channel open for async response
  }
});

async function performSync(data) {
  try {
    const response = await fetch(`${API_URL}/api/sync/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await response.json();
  } catch (error) {
    console.error("Matrix Bridge: Sync failed", error);
    return { error: error.message };
  }
}
