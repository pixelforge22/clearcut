// ClearCut Client Application
// API calls always go to the same origin this page is served from.

document.addEventListener("DOMContentLoaded", () => {

    // ─── Configuration ────────────────────────────────────────────────────────
    const API_ORIGIN = window.location.origin;
    const apiKey = "clearcut_dev_key_2026";

    // ─── UI Element References ─────────────────────────────────────────────────
    const apiStatusBadge   = document.querySelector(".api-status-badge");

    const stageUpload      = document.getElementById("stageUpload");
    const stageProcessing  = document.getElementById("stageProcessing");
    const stageResult      = document.getElementById("stageResult");
    const workspaceCard    = document.getElementById("workspaceCard");

    const dropzone         = document.getElementById("dropzone");
    const fileInput        = document.getElementById("fileInput");
    const selectFileBtn    = document.getElementById("selectFileBtn");
    const imageUrlInput    = document.getElementById("imageUrlInput");
    const submitUrlBtn     = document.getElementById("submitUrlBtn");

    const processingStatus = document.getElementById("processingStatus");
    const processingDetail = document.getElementById("processingDetail");
    const progressBar      = document.getElementById("progressBar");

    const resetBtn         = document.getElementById("resetBtn");
    const toast            = document.getElementById("toast");

    // ─── Helper: build a full URL to an API endpoint ───────────────────────────
    function apiUrl(endpoint) { return `${API_ORIGIN}${endpoint}`; }
    function currentKey()     { return apiKey; }

    // ─── Stage management ──────────────────────────────────────────────────────
    function showStage(name) {
        stageUpload.classList.add("hidden");
        stageProcessing.classList.add("hidden");
        stageResult.classList.add("hidden");
        workspaceCard.classList.remove("editing");

        if (name === "upload")     stageUpload.classList.remove("hidden");
        if (name === "processing") stageProcessing.classList.remove("hidden");
        if (name === "result") {
            stageResult.classList.remove("hidden");
            workspaceCard.classList.add("editing");
        }
    }

    function setLoader(status, detail, pct) {
        processingStatus.textContent = status;
        processingDetail.textContent = detail;
        progressBar.style.width      = `${pct}%`;
    }

    // ─── API Health Check ──────────────────────────────────────────────────────
    async function checkApiHealth() {
        try {
            const res = await fetch(apiUrl("/health"), { method: "GET" });
            if (res.ok) {
                const data = await res.json();
                if (data.status === "healthy") {
                    apiStatusBadge.classList.remove("error");
                    apiStatusBadge.innerHTML = '<span class="status-dot"></span> API Connected';
                    return;
                }
            }
            throw new Error("unhealthy");
        } catch {
            apiStatusBadge.classList.add("error");
            apiStatusBadge.innerHTML = '<span class="status-dot"></span> Connection Error';
        }
    }

    checkApiHealth();
    setInterval(checkApiHealth, 20000);

    // ─── File / URL Input Handling ─────────────────────────────────────────────
    // ─── Browse button ─────────────────────────────────────────────────────────
    selectFileBtn.addEventListener("click", e => {
        e.stopPropagation(); // prevent event reaching dropzone
        fileInput.click();
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) processFile(fileInput.files[0]);
    });

    dropzone.addEventListener("dragover",  e => { e.preventDefault(); dropzone.classList.add("dragover"); });
    dropzone.addEventListener("dragleave", ()  => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", e => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) processFile(e.dataTransfer.files[0]);
    });

    submitUrlBtn.addEventListener("click", () => {
        const url = imageUrlInput.value.trim();
        if (url) processUrl(url);
        else showToast("Please enter a valid image URL.");
    });

    // ─── Core Processing Functions ─────────────────────────────────────────────
    async function processFile(file) {
        const fd = new FormData();
        fd.append("file", file);
        await sendRequest(fd);
    }

    async function processUrl(url) {
        const fd = new FormData();
        fd.append("url", url);
        await sendRequest(fd);
    }

    async function sendRequest(formData) {
        showStage("processing");
        setLoader("Uploading image…", "Sending to server", 15);

        try {
            const res = await fetch(apiUrl("/v1/remove-background?format=json"), {
                method:  "POST",
                headers: { "X-API-Key": currentKey() },
                body:    formData
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: "Request failed." }));
                throw new Error(err.detail || "Server error.");
            }

            const data = await res.json();
            setLoader("Processing image…", "Running U²-Net background removal…", 50);

            if (data.status === "pending" || data.status === "processing") {
                pollJob(data.job_id);
            } else if (data.status === "completed") {
                await fetchResultAndEdit(data.result_url);
            }
        } catch (err) {
            showStage("upload");
            showToast(err.message || "An unexpected error occurred.");
        }
    }

    async function pollJob(jobId) {
        const pollUrl = apiUrl(`/v1/jobs/${jobId}`);
        let attempts  = 0;

        const timer = setInterval(async () => {
            if (++attempts > 90) {
                clearInterval(timer);
                showStage("upload");
                showToast("Processing timed out — please try again.");
                return;
            }
            try {
                const res = await fetch(pollUrl, { headers: { "X-API-Key": currentKey() } });
                if (!res.ok) throw new Error();
                const job = await res.json();

                if (job.status === "processing") {
                    setLoader("Removing background…", "This may take a moment…", 70);
                } else if (job.status === "completed") {
                    clearInterval(timer);
                    setLoader("Finalising…", "Downloading transparent PNG", 90);
                    await fetchResultAndEdit(job.result_url);
                } else if (job.status === "failed") {
                    clearInterval(timer);
                    showStage("upload");
                    showToast(`Processing failed: ${job.error_message}`);
                }
            } catch {
                clearInterval(timer);
                showStage("upload");
                showToast("Lost connection while checking job status.");
            }
        }, 1000);
    }

    async function fetchResultAndEdit(resultEndpoint) {
        try {
            const res = await fetch(apiUrl(resultEndpoint), {
                headers: { "X-API-Key": currentKey() }
            });
            if (!res.ok) throw new Error("Failed to fetch processed image.");

            const blob = await res.blob();
            showStage("result");
            Editor.init(blob);         // Hand the processed PNG blob to the editor
        } catch (err) {
            showStage("upload");
            showToast(err.message || "Failed to retrieve result image.");
        }
    }

    // ─── Reset ─────────────────────────────────────────────────────────────────
    resetBtn.addEventListener("click", () => {
        fileInput.value     = "";
        imageUrlInput.value = "";
        Editor.reset();
        showStage("upload");
    });

    // ─── Toast ─────────────────────────────────────────────────────────────────
    function showToast(msg) {
        toast.textContent = msg;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 3500);
    }

    // ─── Wire editor UI LAST so any error here never breaks uploads ────────────
    try { Editor.wireUI(); } catch (e) { console.warn("Editor init error:", e); }
});
