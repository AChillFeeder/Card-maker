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
const tabButtons = Array.from(document.querySelectorAll(".form-tabs .tab"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));

let activeObjectUrl = null;

const presets = {
  mini: {
    width: 300,
    height: 420,
    dpr: 2,
    format: "png",
    bgScale: 100,
    bgOffsetX: 0,
    bgOffsetY: 0,
    mainScale: 92,
    mainOffsetX: 0,
    mainOffsetY: 0,
  },
  standard: {
    width: 384,
    height: 576,
    dpr: 3,
    format: "png",
    bgScale: 100,
    bgOffsetX: 0,
    bgOffsetY: 0,
    mainScale: 92,
    mainOffsetX: 0,
    mainOffsetY: 0,
  },
  wide: {
    width: 768,
    height: 1024,
    dpr: 2,
    format: "jpeg",
    bgScale: 100,
    bgOffsetX: 0,
    bgOffsetY: -20,
    mainScale: 88,
    mainOffsetX: 0,
    mainOffsetY: -12,
  },
};

const presetLabels = {
  mini: "Mini",
  standard: "Classique",
  wide: "Affiche",
};

const syncPairs = new Map();

function syncValue(control, value) {
  if (!control) {
    return;
  }
  control.value = value;
  const partner = syncPairs.get(control);
  if (partner) {
    partner.value = value;
  }
}

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

function activateTab(target) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tab === target;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.tab === target;
    panel.classList.toggle("is-active", isActive);
    panel.toggleAttribute("hidden", !isActive);
    panel.setAttribute("tabindex", isActive ? "0" : "-1");
  });
}

if (tabButtons.length) {
  activateTab(tabButtons[0].dataset.tab);
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activateTab(button.dataset.tab);
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
  syncValue(form.bgScale, String(preset.bgScale));
  syncValue(form.bgOffsetX, String(preset.bgOffsetX));
  syncValue(form.bgOffsetY, String(preset.bgOffsetY));
  syncValue(form.mainScale, String(preset.mainScale));
  syncValue(form.mainOffsetX, String(preset.mainOffsetX));
  syncValue(form.mainOffsetY, String(preset.mainOffsetY));
  const label = presetLabels[key] || key;
  statusMessage.textContent = `Préréglage ${label} appliqué. Relancez l'aperçu pour visualiser le rendu.`;
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
    const card = input.closest(".upload-card");
    if (card) {
      card.classList.remove("has-error");
    }
    if ([...form.querySelectorAll('input[type="file"]')].every((el) => el.files.length)) {
      statusMessage.textContent = "Fichiers prêts. Ajustez les paramètres puis lancez le rendu.";
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

function validateBeforeRender() {
  const requiredFileInputs = Array.from(form.querySelectorAll('input[type="file"][required]'));
  const missingFiles = requiredFileInputs.filter((input) => !input.files.length);

  requiredFileInputs.forEach((input) => {
    const card = input.closest(".upload-card");
    if (card) {
      card.classList.toggle("has-error", missingFiles.includes(input));
    }
  });

  if (missingFiles.length) {
    statusMessage.textContent = "Ajoutez les images requises avant de lancer le rendu.";
    return false;
  }

  if (typeof form.checkValidity === "function") {
    const isValid = form.checkValidity();
    if (!isValid) {
      const firstInvalid = form.querySelector(":invalid");
      if (firstInvalid) {
        const targetPanel = firstInvalid.closest(".tab-panel");
        if (targetPanel && !targetPanel.classList.contains("is-active")) {
          activateTab(targetPanel.dataset.tab);
        }
        firstInvalid.focus?.({ preventScroll: true });
      }
      try {
        form.reportValidity?.();
      } catch (error) {
        console.warn("Impossible d'afficher les erreurs de validation automatiquement.", error);
      }
      return false;
    }
  }

  return true;
}

async function render(trigger = "preview") {
  if (!validateBeforeRender()) {
    return;
  }

  statusMessage.textContent = trigger === "download"
    ? "Génération d'un rendu optimisé pour le téléchargement."
    : "Génération de l'aperçu.";

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
      downloadLink.download = `carte.${extension}`;
      downloadLink.setAttribute("aria-disabled", "false");
    }

    statusMessage.textContent = trigger === "download"
      ? "Rendu terminé. Le téléchargement va démarrer."
      : "Aperçu mis à jour avec succès.";

    if (trigger === "download") {
      if (downloadLink) {
        setTimeout(() => downloadLink.click(), 50);
      } else {
        const tempLink = document.createElement("a");
        tempLink.href = activeObjectUrl;
        tempLink.download = `carte.${extension}`;
        document.body.appendChild(tempLink);
        tempLink.click();
        tempLink.remove();
      }
    }
  } catch (error) {
    console.error(error);
    statusMessage.textContent = `Le rendu a échoué : ${error.message || error}`;
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
statusMessage.textContent = "Déposez vos images pour commencer.";
updateIconSelection();



