// ─── ClearCut Editor Engine ────────────────────────────────────────────────
// Handles canvas painting (erase / restore / magic-erase), adjustments,
// history (undo/redo), and multi-format export.
// All coordinate math accounts for canvas CSS scaling.

const Editor = (() => {

  /* ── Private state ───────────────────────────────────────────────────── */
  let canvas, ctx
  let imageWidth = 0, imageHeight = 0
  let originalData   // Uint8ClampedArray – AI output, immutable
  let alphaOverride  // Uint8Array per pixel: 0=erased | 1=AI-alpha | 2=restored

  const adj = { brightness: 0, contrast: 0, saturation: 0 }
  const bg  = { enabled: false, color: '#ffffff' }

  let tool          = 'erase'
  let brushSize     = 28     // apparent screen-px diameter
  let brushHardness = 75     // 0–100
  let magicTol      = 35     // flood-fill colour tolerance

  let isDrawing = false
  let lastX = 0, lastY = 0

  // History stack
  const history = []
  let histIdx   = -1
  const MAX_HIST = 30

  /* ── DOM shortcut ────────────────────────────────────────────────────── */
  const el = id => document.getElementById(id)

  /* ── Coordinate helpers ──────────────────────────────────────────────── */
  function toImg(clientX, clientY) {
    const r = canvas.getBoundingClientRect()
    return {
      x: Math.round((clientX - r.left) * imageWidth  / r.width),
      y: Math.round((clientY - r.top)  * imageHeight / r.height)
    }
  }

  function brushRadiusPx() {
    const r = canvas.getBoundingClientRect()
    // Convert screen-px brush radius → image-px radius
    return Math.max(1, Math.ceil((brushSize / 2) * imageWidth / r.width))
  }

  /* ── Pixel math ──────────────────────────────────────────────────────── */
  function clamp(v) { return v < 0 ? 0 : v > 255 ? 255 : v }

  function applyAdj(r, g, b) {
    // Brightness
    const bright = adj.brightness * 2.55
    r = clamp(r + bright); g = clamp(g + bright); b = clamp(b + bright)
    // Contrast
    const cf = (adj.contrast / 100) + 1
    r = clamp((r - 128) * cf + 128)
    g = clamp((g - 128) * cf + 128)
    b = clamp((b - 128) * cf + 128)
    // Saturation via luminance
    const lum = 0.299 * r + 0.587 * g + 0.114 * b
    const sf  = (adj.saturation / 100) + 1
    r = clamp(lum + sf * (r - lum))
    g = clamp(lum + sf * (g - lum))
    b = clamp(lum + sf * (b - lum))
    return [r, g, b]
  }

  /* ── Render (dirty-region for performance) ───────────────────────────── */
  function renderRegion(rx, ry, rw, rh) {
    if (!canvas || rw <= 0 || rh <= 0) return
    console.log(`[Editor] Rendering region: x=${rx}, y=${ry}, w=${rw}, h=${rh}`);
    const imgData = ctx.createImageData(rw, rh)
    const out = imgData.data
    const src = originalData

    for (let dy = 0; dy < rh; dy++) {
      for (let dx = 0; dx < rw; dx++) {
        const px   = rx + dx
        const py   = ry + dy
        const sIdx = (py * imageWidth + px) * 4
        const dIdx = (dy * rw + dx) * 4

        let r = src[sIdx], g = src[sIdx + 1], b = src[sIdx + 2]
        let a = src[sIdx + 3]

        const ov = alphaOverride[py * imageWidth + px]
        if (ov === 0) { a = 0 }
        else if (ov === 2) { a = 255 }
        // ov === 1 → keep AI alpha unchanged

        if (a > 0) { [r, g, b] = applyAdj(r, g, b) }

        out[dIdx] = r; out[dIdx + 1] = g
        out[dIdx + 2] = b; out[dIdx + 3] = a
      }
    }
    ctx.putImageData(imgData, rx, ry)
  }

  function renderFull() { renderRegion(0, 0, imageWidth, imageHeight) }

  /* ── Brush engine ────────────────────────────────────────────────────── */
  function applyBrushAt(imgX, imgY) {
    const rad  = brushRadiusPx()
    const hardF = brushHardness / 100
    const x0 = Math.max(0, imgX - rad)
    const y0 = Math.max(0, imgY - rad)
    const x1 = Math.min(imageWidth  - 1, imgX + rad)
    const y1 = Math.min(imageHeight - 1, imgY + rad)

    console.log(`[Editor] Brush at: x=${imgX}, y=${imgY}, rad=${rad}, tool=${tool}`);

    let changed = false
    for (let py = y0; py <= y1; py++) {
      for (let px = x0; px <= x1; px++) {
        const dist = Math.sqrt((px - imgX) ** 2 + (py - imgY) ** 2)
        if (dist > rad) continue

        // Hardness falloff: full strength inside hardF zone, fade to 0 at edge
        const nd = dist / (rad + 0.001)
        const str = nd <= hardF ? 1 : Math.max(0, 1 - (nd - hardF) / (1 - hardF + 0.001))
        if (str < 0.12) continue

        const idx = py * imageWidth + px
        if (tool === 'erase'   && alphaOverride[idx] !== 0) { alphaOverride[idx] = 0; changed = true }
        if (tool === 'restore' && alphaOverride[idx] !== 2) { alphaOverride[idx] = 2; changed = true }
      }
    }
    console.log(`[Editor] Changed pixels: ${changed}`);
    if (changed) renderRegion(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
  }

  /* ── Magic Erase – BFS flood fill ───────────────────────────────────── */
  function magicErase(imgX, imgY) {
    if (imgX < 0 || imgX >= imageWidth || imgY < 0 || imgY >= imageHeight) return
    const src  = originalData
    const sIdx = (imgY * imageWidth + imgX) * 4
    const sR = src[sIdx], sG = src[sIdx + 1], sB = src[sIdx + 2]

    const visited = new Uint8Array(imageWidth * imageHeight)
    const queue   = [imgY * imageWidth + imgX]
    let head      = 0
    visited[queue[0]] = 1

    let minX = imgX, maxX = imgX, minY = imgY, maxY = imgY

    while (head < queue.length) {
      const pos = queue[head++]
      const px  = pos % imageWidth
      const py  = (pos / imageWidth) | 0
      const si  = pos * 4

      if (src[si + 3] === 0) continue

      const diff = Math.sqrt(
        (src[si]   - sR) ** 2 +
        (src[si+1] - sG) ** 2 +
        (src[si+2] - sB) ** 2
      )
      if (diff > magicTol) continue

      alphaOverride[pos] = 0
      if (px < minX) minX = px; if (px > maxX) maxX = px
      if (py < minY) minY = py; if (py > maxY) maxY = py

      const ns = [pos - 1, pos + 1, pos - imageWidth, pos + imageWidth]
      for (const n of ns) {
        if (n < 0 || n >= imageWidth * imageHeight) continue
        const nx = n % imageWidth
        // Prevent wrap-around on left/right edges
        if (Math.abs(nx - px) > 1) continue
        if (!visited[n]) { visited[n] = 1; queue.push(n) }
      }
    }

    saveHistory()
    renderRegion(
      Math.max(0, minX - 1), Math.max(0, minY - 1),
      Math.min(imageWidth,  maxX - minX + 3),
      Math.min(imageHeight, maxY - minY + 3)
    )
  }

  /* ── History ─────────────────────────────────────────────────────────── */
  function saveHistory() {
    history.splice(histIdx + 1)
    history.push(new Uint8Array(alphaOverride))
    if (history.length > MAX_HIST) history.shift()
    histIdx = history.length - 1
    syncHistBtns()
  }

  function undo() {
    if (histIdx > 0) { histIdx--; alphaOverride.set(history[histIdx]); renderFull(); syncHistBtns() }
  }
  function redo() {
    if (histIdx < history.length - 1) { histIdx++; alphaOverride.set(history[histIdx]); renderFull(); syncHistBtns() }
  }
  function syncHistBtns() {
    el('undoBtn').disabled = histIdx <= 0
    el('redoBtn').disabled = histIdx >= history.length - 1
  }

  /* ── Export ──────────────────────────────────────────────────────────── */
  async function exportAs(format) {
    const exp = document.createElement('canvas')
    exp.width  = imageWidth
    exp.height = imageHeight
    const ec = exp.getContext('2d')

    if (format === 'jpeg' && bg.enabled) {
      ec.fillStyle = bg.color
      ec.fillRect(0, 0, imageWidth, imageHeight)
    }
    ec.drawImage(canvas, 0, 0)

    const ts  = Date.now()
    const ext = format === 'jpeg' ? 'jpg' : format

    if (format === 'svg') {
      const dataUrl = exp.toDataURL('image/png')
      const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="${imageWidth}" height="${imageHeight}" viewBox="0 0 ${imageWidth} ${imageHeight}">
  <image href="${dataUrl}" width="${imageWidth}" height="${imageHeight}"/>
</svg>`
      dlBlob(new Blob([svg], { type: 'image/svg+xml' }), `clearcut_${ts}.svg`)
      return
    }

    const mimes = { png: 'image/png', jpeg: 'image/jpeg', webp: 'image/webp' }
    const quals = { jpeg: 0.95, webp: 0.92 }
    exp.toBlob(b => dlBlob(b, `clearcut_${ts}.${ext}`), mimes[format], quals[format])
  }

  function dlBlob(blob, name) {
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob), download: name
    })
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1500)
  }

  /* ── Cursor ──────────────────────────────────────────────────────────── */
  function updateCursor() {
    if (!canvas) return
    if (window.matchMedia('(pointer: coarse)').matches) {
      canvas.style.cursor = 'crosshair'  // Mobile: no cursor needed
      return
    }
    if (tool === 'magic') { canvas.style.cursor = 'crosshair'; return }
    const d = Math.max(8, brushSize)
    const h = d / 2
    const stroke = tool === 'erase' ? '#FF5555' : '#55FF88'
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${d}' height='${d}'><circle cx='${h}' cy='${h}' r='${h - 1.5}' stroke='${stroke}' stroke-width='1.8' fill='rgba(255,255,255,0.05)'/></svg>`
    canvas.style.cursor = `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${h} ${h}, crosshair`
  }

  /* ── Tool setter ─────────────────────────────────────────────────────── */
  function setTool(t) {
    tool = t
    document.querySelectorAll('.tool-btn').forEach(b => b.classList.toggle('active', b.dataset.tool === t))
    const isMagic = t === 'magic'
    el('brushControls').style.display  = isMagic ? 'none'  : 'flex'
    el('toleranceGroup').style.display = isMagic ? 'flex'  : 'none'
    updateCursor()
  }

  /* ── Events ──────────────────────────────────────────────────────────── */
  function setupEvents() {

    /* Canvas pointer events (covers mouse + touch + stylus) */
    if (canvas) {
      canvas.addEventListener('pointerdown', e => {
        e.preventDefault()
        canvas.setPointerCapture(e.pointerId)
        isDrawing = true
        const { x, y } = toImg(e.clientX, e.clientY)
        lastX = x; lastY = y
        if (tool === 'magic') {
          saveHistory(); magicErase(x, y); isDrawing = false; return
        }
        applyBrushAt(x, y)
      })

      canvas.addEventListener('pointermove', e => {
        if (!isDrawing) return
        e.preventDefault()
        const { x, y } = toImg(e.clientX, e.clientY)
        const dx = x - lastX, dy = y - lastY
        const steps = Math.max(1, Math.ceil(Math.sqrt(dx * dx + dy * dy) / 3))
        for (let s = 1; s <= steps; s++) {
          applyBrushAt(Math.round(lastX + dx * s / steps), Math.round(lastY + dy * s / steps))
        }
        lastX = x; lastY = y
      })

      const stopDraw = () => { if (isDrawing) { saveHistory(); isDrawing = false } }
      canvas.addEventListener('pointerup', stopDraw)
      canvas.addEventListener('pointercancel', stopDraw)
    }

    /* Keyboard shortcuts (desktop) */
    document.addEventListener('keydown', e => {
      const stageRes = el('stageResult')
      if (!stageRes || stageRes.classList.contains('hidden')) return
      if (e.ctrlKey && e.key === 'z') { e.preventDefault(); undo() }
      if (e.ctrlKey && e.key === 'y') { e.preventDefault(); redo() }
      if (!e.ctrlKey && e.key === 'e') setTool('erase')
      if (!e.ctrlKey && e.key === 'r') setTool('restore')
      if (!e.ctrlKey && e.key === 'm') setTool('magic')
      if (e.key === '[') {
        brushSize = Math.max(4, brushSize - 4)
        const bs = el('brushSize'); if (bs) bs.value = brushSize
        const bsv = el('brushSizeVal'); if (bsv) bsv.textContent = `${brushSize}px`
        updateCursor()
      }
      if (e.key === ']') {
        brushSize = Math.min(120, brushSize + 4)
        const bs = el('brushSize'); if (bs) bs.value = brushSize
        const bsv = el('brushSizeVal'); if (bsv) bsv.textContent = `${brushSize}px`
        updateCursor()
      }
    })

    /* Tool buttons */
    document.querySelectorAll('.tool-btn').forEach(b =>
      b.addEventListener('click', () => setTool(b.dataset.tool))
    )

    /* Sliders */
    const sliderMap = {
      brushSize:     v => { brushSize = +v; const l = el('brushSizeVal'); if (l) l.textContent = `${v}px`; updateCursor() },
      brushHardness: v => { brushHardness = +v; const l = el('brushHardnessVal'); if (l) l.textContent = `${v}%` },
      tolerance:     v => { magicTol = +v; const l = el('toleranceVal'); if (l) l.textContent = v },
      brightness:    v => { adj.brightness = +v; const l = el('brightnessVal'); if (l) l.textContent = v; renderFull() },
      contrast:      v => { adj.contrast = +v; const l = el('contrastVal'); if (l) l.textContent = v; renderFull() },
      saturation:    v => { adj.saturation = +v; const l = el('saturationVal'); if (l) l.textContent = v; renderFull() },
    }
    Object.entries(sliderMap).forEach(([id, fn]) => {
      const inp = el(id); if (inp) inp.addEventListener('input', () => fn(inp.value))
    })

    /* Undo / Redo / Reset */
    const undoBtn = el('undoBtn'); if (undoBtn) undoBtn.addEventListener('click', undo)
    const redoBtn = el('redoBtn'); if (redoBtn) redoBtn.addEventListener('click', redo)
    const resetMaskBtn = el('resetMaskBtn')
    if (resetMaskBtn) resetMaskBtn.addEventListener('click', () => { alphaOverride.fill(1); saveHistory(); renderFull() })

    /* Adjustment reset */
    const resetAdjBtn = el('resetAdjBtn')
    if (resetAdjBtn) resetAdjBtn.addEventListener('click', () => {
      adj.brightness = adj.contrast = adj.saturation = 0
      ;['brightness', 'contrast', 'saturation'].forEach(k => {
        const inp = el(k); if (inp) inp.value = 0
        const val = el(`${k}Val`); if (val) val.textContent = '0'
      })
      renderFull()
    })

    /* Background fill */
    const bgTog = el('bgColorToggle')
    if (bgTog) bgTog.addEventListener('change', e => {
      bg.enabled = e.target.checked
      const bgp = el('bgColorPicker'); if (bgp) bgp.disabled = !bg.enabled
      const swr = el('swatchesRow'); if (swr) swr.classList.toggle('swatches-active', bg.enabled)
    })
    const bgPicker = el('bgColorPicker')
    if (bgPicker) bgPicker.addEventListener('input', e => { bg.color = e.target.value })
    document.querySelectorAll('.swatch').forEach(sw =>
      sw.addEventListener('click', () => {
        bg.color   = sw.dataset.color
        bg.enabled = true
        const bgt = el('bgColorToggle'); if (bgt) { bgt.checked = true }
        const bgp = el('bgColorPicker'); if (bgp) { bgp.value = bg.color; bgp.disabled = false }
        const swr = el('swatchesRow');  if (swr) swr.classList.add('swatches-active')
        document.querySelectorAll('.swatch').forEach(s => s.classList.remove('swatch-selected'))
        sw.classList.add('swatch-selected')
      })
    )

    /* Panel tabs */
    document.querySelectorAll('.panel-tab').forEach(tab =>
      tab.addEventListener('click', () => {
        document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'))
        document.querySelectorAll('.panel-content').forEach(c => c.classList.remove('active'))
        tab.classList.add('active')
        const tContent = el(`tab-${tab.dataset.tab}`)
        if (tContent) tContent.classList.add('active')
        // Expand panel on mobile when tab is tapped
        const ep = el('editorPanel')
        if (ep) ep.classList.remove('panel-collapsed')
      })
    )

    /* Mobile bottom-sheet handle toggle */
    const handle = el('panelHandle')
    if (handle) handle.addEventListener('click', () => {
      const ep = el('editorPanel')
      if (ep) ep.classList.toggle('panel-collapsed')
    })

    /* Export buttons */
    ;['Png', 'Jpeg', 'Webp', 'Svg'].forEach(f => {
      const btn = el(`export${f}`)
      if (btn) btn.addEventListener('click', () => exportAs(f.toLowerCase()))
    })
  }

  /* ── Init ────────────────────────────────────────────────────────────── */
  function init(blob) {
    const img    = new Image()
    const objUrl = URL.createObjectURL(blob)

    img.onload = () => {
      imageWidth  = img.naturalWidth
      imageHeight = img.naturalHeight

      canvas = el('editorCanvas')
      ctx    = canvas.getContext('2d', { willReadFrequently: true })
      canvas.width  = imageWidth
      canvas.height = imageHeight

      ctx.drawImage(img, 0, 0)
      const raw    = ctx.getImageData(0, 0, imageWidth, imageHeight)
      originalData = new Uint8ClampedArray(raw.data)

      alphaOverride = new Uint8Array(imageWidth * imageHeight).fill(1)

      // Reset adjustments UI
      adj.brightness = adj.contrast = adj.saturation = 0
      ;['brightness', 'contrast', 'saturation'].forEach(k => {
        const inp = el(k); if (inp) inp.value = 0
        const val = el(`${k}Val`); if (val) val.textContent = '0'
      })
      bg.enabled = false
      const bgt = el('bgColorToggle'); if (bgt) bgt.checked = false
      const bgp = el('bgColorPicker'); if (bgp) bgp.disabled = true
      const swr = el('swatchesRow'); if (swr) swr.classList.remove('swatches-active')

      // Reset tool state
      tool = 'erase'
      document.querySelectorAll('.tool-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.tool === 'erase')
      )
      setTool('erase')

      // Reset history
      history.length = 0; histIdx = -1
      saveHistory()
      renderFull()
      updateCursor()

      const info = el('canvasInfo')
      if (info) info.textContent = `${imageWidth} × ${imageHeight} px`

      // Start panel collapsed on mobile
      if (window.innerWidth < 768) {
        el('editorPanel').classList.add('panel-collapsed')
      }

      URL.revokeObjectURL(objUrl)
    }
    img.src = objUrl
  }

  /* ── Reset ───────────────────────────────────────────────────────────── */
  function reset() {
    imageWidth = imageHeight = 0
    originalData = alphaOverride = null
    history.length = 0; histIdx = -1
    isDrawing = false
    if (canvas) { canvas.width = 0; canvas.height = 0 }
  }

  /* ── First-time event wiring (called once on DOMContentLoaded) ───────── */
  function wireUI() {
    canvas = el('editorCanvas')
    if (canvas) {
      ctx = canvas.getContext('2d', { willReadFrequently: true })
    }
    setupEvents()
  }

  return { init, reset, wireUI }
})()
