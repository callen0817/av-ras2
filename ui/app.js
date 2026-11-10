// AV Ras2 - Interactive Client Application
// Artificial Vision, Inc.

(function () {
  'use strict';

  // State
  const state = {
    currentFile: null,
    rasterImage: null,
    planData: null,
    viewMode: 'Overlay', // 'Overlay', 'CAD', 'Raster'
    overlayOpacity: 0.65,
    zoom: 1.0,
    panX: 0,
    panY: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    selectedEntity: null,
    calibrationMode: false,
    calibrationPoints: [],
    layerVisibility: {
      'A-WALL': true,
      'A-HATCH': true,
      'A-DOOR': true,
      'A-GLAZ': true,
      'A-COLS': true,
      'A-ANNO': true,
      'AV-REVIEW': true,
    },
    scale: {
      units_per_pixel: 0.05,
      unit: 'ft',
      method: 'auto'
    }
  };

  // DOM Elements
  const canvas = document.getElementById('mainCanvas');
  const ctx = canvas.getContext('2d');
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const statusMsg = document.getElementById('statusMessage');
  const cursorCoord = document.getElementById('cursorCoord');

  // Initialize Canvas Size
  function resizeCanvas() {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    render();
  }
  window.addEventListener('resize', resizeCanvas);

  // Status Logger
  function logStatus(text) {
    statusMsg.textContent = text;
  }

  // --- File Dropzone & Intake ---
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  });

  function handleFile(file) {
    state.currentFile = file;
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileInfo').style.display = 'block';
    logStatus(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload', {
      method: 'POST',
      body: formData,
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          logStatus(`Loaded ${file.name} (${data.width}x${data.height}px). Establishing scale...`);
          loadImageFromBase64(data.image_b64, () => {
            fitToView();
            // Automatically run conversion pipeline
            runConversion();
          });
        } else {
          logStatus(`Upload error: ${data.error}`);
        }
      })
      .catch(err => {
        logStatus(`Connection error: ${err}`);
      });
  }

  function loadImageFromBase64(b64, callback) {
    const img = new Image();
    img.onload = () => {
      state.rasterImage = img;
      if (callback) callback();
      render();
    };
    img.src = 'data:image/png;base64,' + b64;
  }

  // --- Conversion Pipeline Trigger ---
  document.getElementById('btnRunConversion').addEventListener('click', runConversion);

  function runConversion() {
    if (!state.currentFile) {
      alert('Please upload a raster plan first.');
      return;
    }

    logStatus('AV Ras2 Engine: Reconstructing geometry, walls, and hatches...');
    const unit = document.getElementById('selUnits').value;
    const snapTol = parseFloat(document.getElementById('rngSnapTol').value);

    fetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        unit: unit,
        snap_distance_px: snapTol,
        calibration_points: state.calibrationPoints.length === 2 ? state.calibrationPoints : null,
        real_distance: parseFloat(document.getElementById('inputRealDist').value) || 10.0,
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          state.planData = data.plan;
          updateQAMetrics(data.plan.qa_report);
          updateScaleInfo(data.plan.scale);
          enableExports();
          logStatus(`Conversion complete! QA Coverage: ${data.plan.qa_report.raster_coverage_pct}%`);
          render();
        } else {
          logStatus(`Conversion failed: ${data.error}`);
        }
      })
      .catch(err => logStatus(`Error: ${err}`));
  }

  function updateQAMetrics(qa) {
    document.getElementById('metricCoverage').textContent = `${qa.raster_coverage_pct}%`;
    document.getElementById('metricWalls').textContent = qa.walls_detected;
    document.getElementById('metricHatches').textContent = qa.hatch_regions;
    document.getElementById('metricDoors').textContent = qa.doors_detected;
    document.getElementById('metricResidual').textContent = qa.calibration_residual.toFixed(4);
    document.getElementById('metricQAStatus').textContent = qa.status;
  }

  function updateScaleInfo(scale) {
    state.scale = scale;
    document.getElementById('scaleRatioDisplay').textContent =
      `${scale.units_per_pixel.toFixed(6)} ${scale.unit}/px`;
  }

  function enableExports() {
    ['btnExportDXF', 'btnDownloadDXF', 'btnDownloadSVG', 'btnDownloadPDF', 'btnDownloadOverlay']
      .forEach(id => {
        const el = document.getElementById(id);
        if (el) el.removeAttribute('disabled');
      });
  }

  // --- Export Actions ---
  document.getElementById('btnDownloadDXF').addEventListener('click', () => downloadFile('/api/download/dxf', 'drawing.dxf'));
  document.getElementById('btnExportDXF').addEventListener('click', () => downloadFile('/api/download/dxf', 'drawing.dxf'));
  document.getElementById('btnDownloadSVG').addEventListener('click', () => downloadFile('/api/download/svg', 'vector.svg'));
  document.getElementById('btnDownloadPDF').addEventListener('click', () => downloadFile('/api/download/pdf', 'drawing.pdf'));
  document.getElementById('btnDownloadOverlay').addEventListener('click', () => downloadFile('/api/download/overlay', 'overlay.png'));

  function downloadFile(url, defaultName) {
    const a = document.createElement('a');
    a.href = url;
    a.download = defaultName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // --- View Toolbar Controls ---
  const modeButtons = {
    'Overlay': document.getElementById('modeOverlay'),
    'CAD': document.getElementById('modeCAD'),
    'Raster': document.getElementById('modeRaster'),
  };

  Object.entries(modeButtons).forEach(([mode, btn]) => {
    btn.addEventListener('click', () => {
      state.viewMode = mode;
      Object.values(modeButtons).forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      render();
    });
  });

  const rngOpacity = document.getElementById('rngOpacity');
  rngOpacity.addEventListener('input', (e) => {
    state.overlayOpacity = parseInt(e.target.value, 10) / 100.0;
    render();
  });

  document.getElementById('btnZoomIn').addEventListener('click', () => { state.zoom *= 1.25; render(); });
  document.getElementById('btnZoomOut').addEventListener('click', () => { state.zoom /= 1.25; render(); });
  document.getElementById('btnFitView').addEventListener('click', fitToView);

  function fitToView() {
    if (!state.rasterImage) return;
    const padding = 40;
    const availW = canvas.width - padding * 2;
    const availH = canvas.height - padding * 2;
    const scaleX = availW / state.rasterImage.width;
    const scaleY = availH / state.rasterImage.height;
    state.zoom = Math.min(scaleX, scaleY);
    state.panX = (canvas.width - state.rasterImage.width * state.zoom) / 2;
    state.panY = (canvas.height - state.rasterImage.height * state.zoom) / 2;
    render();
  }

  // --- Layer Visibility Checkboxes ---
  const layerCheckboxMap = {
    'chkLayerWall': 'A-WALL',
    'chkLayerHatch': 'A-HATCH',
    'chkLayerDoor': 'A-DOOR',
    'chkLayerGlaz': 'A-GLAZ',
    'chkLayerCols': 'A-COLS',
    'chkLayerAnno': 'A-ANNO',
    'chkLayerReview': 'AV-REVIEW',
  };

  Object.entries(layerCheckboxMap).forEach(([chkId, layerKey]) => {
    const el = document.getElementById(chkId);
    if (el) {
      el.addEventListener('change', (e) => {
        state.layerVisibility[layerKey] = e.target.checked;
        render();
      });
    }
  });

  // --- Canvas Interaction (Pan, Zoom, Measurement, Selection) ---
  canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0) { // Left click
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      if (state.calibrationMode) {
        const px = (mouseX - state.panX) / state.zoom;
        const py = (mouseY - state.panY) / state.zoom;
        state.calibrationPoints.push([px, py]);
        if (state.calibrationPoints.length === 2) {
          state.calibrationMode = false;
          logStatus('2 points picked. Enter known distance and click Apply.');
        }
        render();
        return;
      }

      // Entity Selection
      const hit = findEntityAt(mouseX, mouseY);
      if (hit) {
        state.selectedEntity = hit;
        inspectEntity(hit);
        render();
      } else {
        // Start Pan
        state.isDragging = true;
        state.dragStartX = mouseX - state.panX;
        state.dragStartY = mouseY - state.panY;
      }
    }
  });

  window.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (state.isDragging) {
      state.panX = mouseX - state.dragStartX;
      state.panY = mouseY - state.dragStartY;
      render();
    }

    // Coordinate readout
    if (state.rasterImage) {
      const imgX = (mouseX - state.panX) / state.zoom;
      const imgY = (mouseY - state.panY) / state.zoom;
      const unitsPerPx = state.scale.units_per_pixel || 0.05;
      const cadX = (imgX * unitsPerPx).toFixed(2);
      const cadY = (((state.rasterImage.height - imgY) * unitsPerPx)).toFixed(2);
      cursorCoord.textContent = `CAD X: ${cadX} ${state.scale.unit} | Y: ${cadY} ${state.scale.unit} (Px: ${Math.round(imgX)}, ${Math.round(imgY)})`;
    }
  });

  window.addEventListener('mouseup', () => { state.isDragging = false; });

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newZoom = state.zoom * zoomFactor;

    state.panX = mouseX - (mouseX - state.panX) * zoomFactor;
    state.panY = mouseY - (mouseY - state.panY) * zoomFactor;
    state.zoom = newZoom;
    render();
  }, { passive: false });

  // Calibration 2-point button
  document.getElementById('btnStart2PtCalib').addEventListener('click', () => {
    state.calibrationMode = true;
    state.calibrationPoints = [];
    logStatus('📏 Pick Point 1 on the canvas...');
  });

  document.getElementById('btnApplyManualCalib').addEventListener('click', () => {
    if (state.calibrationPoints.length < 2) {
      alert('Please click "Pick 2 Calibration Points" and click two references first.');
      return;
    }
    runConversion();
  });

  // --- Entity Inspection ---
  function findEntityAt(screenX, screenY) {
    if (!state.planData || !state.planData.entities) return null;
    const imgX = (screenX - state.panX) / state.zoom;
    const imgY = (screenY - state.panY) / state.zoom;
    const tol = 8.0 / state.zoom;

    for (let ent of state.planData.entities) {
      if (!state.layerVisibility[ent.layer]) continue;

      if (ent.entity_type === 'LINE') {
        const s = ent.pixel_geometry.start;
        const e = ent.pixel_geometry.end;
        if (distToSegment(imgX, imgY, s[0], s[1], e[0], e[1]) <= tol) {
          return ent;
        }
      } else if (ent.entity_type === 'HATCH') {
        // Point in polygon test for hatch outer loop
        const outerLoop = ent.pixel_geometry.loops[0];
        if (outerLoop && pointInPoly(imgX, imgY, outerLoop)) {
          return ent;
        }
      } else if (ent.entity_type === 'ARC') {
        const c = ent.pixel_geometry.center;
        const r = ent.pixel_geometry.radius;
        const d = Math.hypot(imgX - c[0], imgY - c[1]);
        if (Math.abs(d - r) <= tol) {
          return ent;
        }
      }
    }
    return null;
  }

  function distToSegment(px, py, x1, y1, x2, y2) {
    const l2 = (x2 - x1)**2 + (y2 - y1)**2;
    if (l2 === 0) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)));
  }

  function pointInPoly(px, py, pts) {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const xi = pts[i][0], yi = pts[i][1];
      const xj = pts[j][0], yj = pts[j][1];
      const intersect = ((yi > py) !== (yj > py)) &&
        (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function inspectEntity(ent) {
    document.getElementById('noEntitySelected').style.display = 'none';
    document.getElementById('entityTable').style.display = 'table';
    document.getElementById('propId').textContent = ent.id;
    document.getElementById('propType').textContent = ent.entity_type;
    document.getElementById('propLayer').textContent = ent.layer;
    document.getElementById('propConf').textContent = `${(ent.confidence * 100).toFixed(0)}%`;
    document.getElementById('propEvidence').textContent = ent.source_evidence;

    const thick = ent.metadata.wall_thickness_cad ? `${ent.metadata.wall_thickness_cad} ${state.scale.unit}` : '--';
    document.getElementById('propThick').textContent = thick;

    if (ent.entity_type === 'LINE') {
      const dx = ent.cad_geometry.end[0] - ent.cad_geometry.start[0];
      const dy = ent.cad_geometry.end[1] - ent.cad_geometry.start[1];
      document.getElementById('propSize').textContent = `${Math.hypot(dx, dy).toFixed(2)} ${state.scale.unit}`;
    } else if (ent.entity_type === 'HATCH') {
      document.getElementById('propSize').textContent = ent.metadata.area_cad ? `${ent.metadata.area_cad} sq ${state.scale.unit}` : '--';
    } else if (ent.entity_type === 'ARC') {
      document.getElementById('propSize').textContent = `R = ${ent.cad_geometry.radius.toFixed(2)} ${state.scale.unit}`;
    } else if (ent.entity_type === 'TEXT') {
      document.getElementById('propSize').textContent = `"${ent.pixel_geometry.text.replace(/\n/g, ' ')}"`;
    }
  }

  // --- Master Rendering Pipeline ---
  function render() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.save();
    ctx.translate(state.panX, state.panY);
    ctx.scale(state.zoom, state.zoom);

    // 1. Draw Base Raster Image
    if (state.rasterImage && state.viewMode !== 'CAD') {
      if (state.viewMode === 'Overlay') {
        ctx.globalAlpha = 1.0 - state.overlayOpacity * 0.6;
      } else {
        ctx.globalAlpha = 1.0;
      }
      ctx.drawImage(state.rasterImage, 0, 0);
      ctx.globalAlpha = 1.0;
    }

    // 2. Draw Reconstructed CAD Geometry
    if (state.planData && state.planData.entities && state.viewMode !== 'Raster') {

      // A. Render Hatch Fills (A-HATCH) first
      if (state.layerVisibility['A-HATCH']) {
        ctx.fillStyle = 'rgba(197, 160, 89, 0.45)'; // Artificial Vision Gold translucent fill
        state.planData.entities
          .filter(e => e.entity_type === 'HATCH')
          .forEach(hatch => {
            ctx.beginPath();
            for (let loop of hatch.pixel_geometry.loops) {
              if (loop.length < 3) continue;
              ctx.moveTo(loop[0][0], loop[0][1]);
              for (let i = 1; i < loop.length; i++) {
                ctx.lineTo(loop[i][0], loop[i][1]);
              }
              ctx.closePath();
            }
            ctx.fill('evenodd');
          });
      }

      // B. Render Linework (A-WALL, A-DOOR, A-GLAZ, A-COLS)
      for (let ent of state.planData.entities) {
        if (!state.layerVisibility[ent.layer]) continue;
        if (ent.entity_type === 'HATCH') continue;

        ctx.beginPath();
        ctx.lineWidth = ent.layer === 'A-WALL' ? 2.5 : 1.5;

        // Layer color
        if (ent.layer === 'A-WALL') ctx.strokeStyle = '#12151a';
        else if (ent.layer === 'A-DOOR') ctx.strokeStyle = '#d9534f';
        else if (ent.layer === 'A-GLAZ') ctx.strokeStyle = '#0288d1';
        else if (ent.layer === 'A-COLS') ctx.strokeStyle = '#2e7d32';
        else ctx.strokeStyle = '#8c96a5';

        if (ent.entity_type === 'TEXT') {
          ctx.save();
          ctx.fillStyle = ent.layer === 'A-DIMS' ? '#0288d1' : '#f57c00';
          const fontSize = Math.max(10, ent.pixel_geometry.height * 0.7);
          ctx.font = `600 ${fontSize}px -apple-system, sans-serif`;
          const textLines = (ent.pixel_geometry.text || '').split('\n');
          textLines.forEach((tLine, lineIdx) => {
            ctx.fillText(tLine.trim(), ent.pixel_geometry.insert[0], ent.pixel_geometry.insert[1] + (lineIdx * fontSize * 1.25));
          });
          ctx.restore();
          continue;
        }

        if (ent.entity_type === 'LINE') {
          const s = ent.pixel_geometry.start;
          const e = ent.pixel_geometry.end;
          ctx.moveTo(s[0], s[1]);
          ctx.lineTo(e[0], e[1]);
          ctx.stroke();
        } else if (ent.entity_type === 'LWPOLYLINE') {
          const pts = ent.pixel_geometry.points;
          if (pts && pts.length >= 2) {
            ctx.moveTo(pts[0][0], pts[0][1]);
            for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
            if (ent.pixel_geometry.is_closed) ctx.closePath();
            ctx.stroke();
          }
        } else if (ent.entity_type === 'ARC') {
          const c = ent.pixel_geometry.center;
          const r = ent.pixel_geometry.radius;
          const sRad = ent.pixel_geometry.start_angle * Math.PI / 180;
          const eRad = ent.pixel_geometry.end_angle * Math.PI / 180;
          ctx.arc(c[0], c[1], r, sRad, eRad);
          ctx.stroke();
        }

        // Highlight selected entity
        if (state.selectedEntity && state.selectedEntity.id === ent.id) {
          ctx.save();
          ctx.lineWidth = 4.0;
          ctx.strokeStyle = '#d4af37'; // Glowing gold
          ctx.stroke();
          ctx.restore();
        }
      }
    }

    // 3. Draw Calibration Line if picking points
    if (state.calibrationPoints.length > 0) {
      ctx.fillStyle = '#d32f2f';
      for (let pt of state.calibrationPoints) {
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], 5, 0, Math.PI * 2);
        ctx.fill();
      }
      if (state.calibrationPoints.length === 2) {
        ctx.beginPath();
        ctx.strokeStyle = '#d32f2f';
        ctx.lineWidth = 2.0;
        ctx.setLineDash([5, 5]);
        ctx.moveTo(state.calibrationPoints[0][0], state.calibrationPoints[0][1]);
        ctx.lineTo(state.calibrationPoints[1][0], state.calibrationPoints[1][1]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    ctx.restore();
  }

  // Initial resize
  resizeCanvas();

  // Load demo synthetic plan if available
  fetch('/api/demo')
    .then(r => r.json())
    .then(data => {
      if (data.available && data.image_b64) {
        document.getElementById('fileName').textContent = data.file_name;
        document.getElementById('fileInfo').style.display = 'block';
        loadImageFromBase64(data.image_b64, () => {
          fitToView();
          state.currentFile = { name: data.file_name };
          runConversion();
        });
      }
    })
    .catch(() => {});

})();
