(async function () {
  const { loadConfig, saveConnection, api } = window.MM;
  const cfg = await loadConfig();
  document.getElementById("apiBase").value = cfg.apiBase;
  document.getElementById("apiToken").value = cfg.token;
  document.getElementById("save").addEventListener("click", async () => {
    const status = document.getElementById("status");
    await saveConnection(document.getElementById("apiBase").value.trim(), document.getElementById("apiToken").value.trim());
    try {
      const h = await api.health();
      await api.meetings();
      status.textContent = `Connected ✓ (${h.models.enabled ? "local Hugging Face models" : "rule-based NLP only"})`;
    } catch (e) { status.textContent = e.message; }
  });
})();
