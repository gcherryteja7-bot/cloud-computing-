const form = document.querySelector("#verification-form");
const resultPanel = document.querySelector("#result");
const submitButton = document.querySelector("#submit-button");

for (const [inputId, nameId] of [
  ["document-image", "document-name"],
  ["selfie-image", "selfie-name"],
]) {
  document.querySelector(`#${inputId}`).addEventListener("change", (event) => {
    const file = event.target.files[0];
    document.querySelector(`#${nameId}`).textContent = file ? file.name : "Choose an image";
  });
}

function showResult(className, heading, message, flags = []) {
  resultPanel.className = `result card ${className}`;
  resultPanel.replaceChildren();
  const title = document.createElement("h2");
  title.textContent = heading;
  const body = document.createElement("p");
  body.textContent = message;
  resultPanel.append(title, body);
  if (flags.length) {
    const list = document.createElement("ul");
    for (const flag of flags) {
      const item = document.createElement("li");
      item.textContent = flag.replaceAll("_", " ");
      list.append(item);
    }
    resultPanel.append(list);
  }
  resultPanel.hidden = false;
  resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  submitButton.firstElementChild.textContent = "Processing images…";
  resultPanel.hidden = true;
  try {
    const formData = new FormData(form);
    const apiKey = document.querySelector("#api-key").value.trim();
    const headers = apiKey ? { "X-API-Key": apiKey } : {};
    const response = await fetch("/api/verify", { method: "POST", headers, body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Verification request failed.");
    const passed = payload.outcome === "checks_passed";
    showResult(
      passed ? "success" : "review",
      passed ? "Automated checks passed" : "Human review needed",
      `${payload.message} OCR readable: ${payload.ocr_readable ? "yes" : "no"}. Face match: ${payload.face_match === null ? "inconclusive" : payload.face_match ? "match" : "no match"}. Reference: ${payload.verification_id}`,
      payload.flags,
    );
  } catch (error) {
    showResult("error", "Could not complete the checks", error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.firstElementChild.textContent = "Run identity checks";
  }
});
