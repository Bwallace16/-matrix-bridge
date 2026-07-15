/**
 * Content script for capturing interactions on Claude and ChatGPT pages.
 */

console.log("Matrix Bridge: Content script loaded");

// Detect which platform we're on
const platform = detectPlatform();

function detectPlatform() {
  const url = window.location.href;
  if (url.includes("claude.ai")) return "claude";
  if (url.includes("chat.openai.com")) return "gpt";
  return null;
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "captureState") {
    const state = captureCurrentState();
    sendResponse({ state, platform });
  }
});

function captureCurrentState() {
  // TODO: Implement state capture logic
  // - Extract conversation history
  // - Get current system prompt
  // - Capture files/artifacts
  return {
    messages: [],
    files: [],
    systemPrompt: ""
  };
}
