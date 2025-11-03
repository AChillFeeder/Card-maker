const form = document.getElementById("card-form");
const previewButton = document.getElementById("btn-preview");
const downloadLink = document.getElementById("download-link");
const statusMessage = document.getElementById("status-message");
const loader = document.getElementById("loader");
const resultImage = document.getElementById("result");
const placeholder = document.querySelector(".preview-placeholder");
const chips = {
  mini: document.getElementById("prefill-mini"),
  standard: document.getElementById("prefill-standard"),
  wide: document.getElementById("prefill-wide"),
};
const iconInputs = document.querySelectorAll('input[name="playstyleIcon"]');

let activeObjectUrl = null;

const presets = {
  mini: { width: 300, height: 420, dpr: 2, format: "png" },
  standard: { width: 384, height: 576, dpr: 3, format: "png" },
  wide: { width: 768, height: 1024, dpr: 2, format: "jpeg" },
};

const syncPairs = new Map();

document.querySelectorAll(".sync-number").forEach((numberInput) => {
  const key = numberInput.dataset.sync;
  if (!key) return;
  const rangeInput = form.querySelector(`.sync-range[data-sync="${key}"]`);
  if (rangeInput) {
    syncPairs.set(numberInput, rangeInput);
    syncPairs.set(rangeInput, numberInput);
  }
});

syncPairs.forEach((target, input) => {
  input.addEventListener("input", () => {
    target.value = input.value;
  });
});

Object.entries(chips).forEach(([presetKey, button]) => {
  button.addEventListener("click", () => applyPreset(presetKey));
});

function updateIconSelection() {
  iconInputs.forEach((input) => {
    const option = input.closest(".icon-option");
    if (option) {
      option.classList.toggle("is-selected", input.checked);
    }
  });
}

iconInputs.forEach((input) => {
  input.addEventListener("change", updateIconSelection);
});

function applyPreset(key) {
  const preset = presets[key];
  if (!preset) return;
  form.width.value = preset.width;
  form.height.value = preset.height;
  form.dpr.value = preset.dpr;
  form.format.value = preset.format;
  statusMessage.textContent = `Applied ${key} preset. Update the preview to render with new dimensions.`;
}

function updateFileLabels() {
  form.querySelectorAll(".upload-card").forEach((wrapper) => {
    const input = wrapper.querySelector('input[type="file"]');
    const label = wrapper.querySelector(".upload-meta");
    if (!input || !label) return;
    const files = Array.from(input.files || []);
    label.textContent = files.length ? files.map((f) => f.name).join(", ") : label.dataset.placeholder;
  });
}

form.querySelectorAll('input[type="file"]').forEach((input) => {
  input.addEventListener("change", () => {
    updateFileLabels();
    if ([...form.querySelectorAll('input[type="file"]')].every((el) => el.files.length)) {
      statusMessage.textContent = "Files ready. Adjust settings and render when ready.";
    }
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    input.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      input.closest(".upload-card").classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    input.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      input.closest(".upload-card").classList.remove("is-dragging");
      if (event.type === "drop" && event.dataTransfer?.files?.length) {
        input.files = event.dataTransfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  });
});

function setLoading(isLoading) {
  loader.hidden = !isLoading;
  previewButton.disabled = isLoading;
  if (isLoading) {
    form.classList.add("is-busy");
  } else {
    form.classList.remove("is-busy");
  }
}

function revokeActiveUrl() {
  if (activeObjectUrl) {
    URL.revokeObjectURL(activeObjectUrl);
    activeObjectUrl = null;
  }
}

async function render(trigger = "preview") {
  if (!form.reportValidity()) {
    return;
  }

  statusMessage.textContent = trigger === "download"
    ? "Rendering a fresh download-ready version…"
    : "Rendering preview…";

  const formData = new FormData(form);

  try {
    setLoading(true);
    const response = await fetch("/api/render-card", { method: "POST", body: formData });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || response.statusText);
    }

    const blob = await response.blob();
    revokeActiveUrl();
    activeObjectUrl = URL.createObjectURL(blob);

    resultImage.src = activeObjectUrl;
    resultImage.style.display = "block";
    placeholder.style.display = "none";

    const format = (formData.get("format") || "png").toString().toLowerCase();
    const extension = format === "pdf" ? "pdf" : format;

    if (downloadLink) {
      downloadLink.href = activeObjectUrl;
      downloadLink.download = `card.${extension}`;
      downloadLink.setAttribute("aria-disabled", "false");
    }

    statusMessage.textContent = trigger === "download"
      ? "Render complete. Download should begin shortly."
      : "Preview updated successfully.";

    if (trigger === "download") {
      if (downloadLink) {
        setTimeout(() => downloadLink.click(), 50);
      } else {
        const tempLink = document.createElement("a");
        tempLink.href = activeObjectUrl;
        tempLink.download = `card.${extension}`;
        document.body.appendChild(tempLink);
        tempLink.click();
        tempLink.remove();
      }
    }
  } catch (error) {
    console.error(error);
    statusMessage.textContent = `Render failed: ${error.message || error}`;
  } finally {
    setLoading(false);
  }
}

previewButton.addEventListener("click", () => render("preview"));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  render("download");
});

if (downloadLink) {
  downloadLink.addEventListener("click", (event) => {
    if (downloadLink.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
    }
  });
}

window.addEventListener("beforeunload", () => {
  revokeActiveUrl();
});

resultImage.addEventListener("load", () => {
  setLoading(false);
});

// Initialise UI state on load
updateFileLabels();
statusMessage.textContent = "Drop in your artwork files to get started.";
updateIconSelection();
