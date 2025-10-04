const config = window.__STUDIO_CONFIG__ || {};
const OPENAPI_URL = config.openapiUrl || '/openapi.json';
const toastState = { timer: null };
let endpointCatalogue = null;
const ytDlpState = {
    metadata: null,
    rawResponse: null,
    formatsById: new Map(),
    dom: {},
    lastTemplate: 'best',
    modalKeyListener: null,
    selectedFormatId: null
};

const COBALT_FIELD_IDS = {
    service: 'cobalt-service',
    downloadMode: 'cobalt-download-mode',
    filenameStyle: 'cobalt-filename-style',
    audioFormat: 'cobalt-audio-format',
    audioBitrate: 'cobalt-audio-bitrate',
    videoQuality: 'cobalt-video-quality',
    youtubeVideoCodec: 'cobalt-youtube-video-codec',
    youtubeVideoContainer: 'cobalt-youtube-video-container',
    localProcessing: 'cobalt-local-processing',
    subtitleLang: 'cobalt-subtitle-lang',
    youtubeDubLang: 'cobalt-youtube-dub-lang'
};

const COBALT_BOOLEAN_FIELDS = {
    alwaysProxy: 'cobalt-always-proxy',
    disableMetadata: 'cobalt-disable-metadata',
    allowH265: 'cobalt-allow-h265',
    tiktokFullAudio: 'cobalt-tiktok-full-audio',
    youtubeBetterAudio: 'cobalt-youtube-better-audio',
    youtubeHLS: 'cobalt-youtube-hls'
};

const COBALT_BOOLEAN_SELECT_FIELDS = {
    convertGif: 'cobalt-convert-gif'
};

function init() {
    setupNavigation();
    setupSectionObserver();
    initialiseResultPanels();
    setupHalationsControls();
    setupBeforeAfterControls();
    setupForms();
    loadEndpointCatalogue();
}

function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach((link) => {
        link.addEventListener('click', () => {
            const targetId = link.dataset.section;
            const target = document.getElementById(targetId);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            navLinks.forEach((btn) => btn.classList.toggle('active', btn === link));
        });
    });
}

function setupSectionObserver() {
    const sections = document.querySelectorAll('main .panel');
    const navLookup = new Map();
    document.querySelectorAll('.nav-link').forEach((link) => {
        navLookup.set(link.dataset.section, link);
    });

    if (!('IntersectionObserver' in window)) {
        return;
    }

    const observer = new IntersectionObserver(
        (entries) => {
            const visible = entries
                .filter((entry) => entry.isIntersecting)
                .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
            if (visible.length) {
                const sectionId = visible[0].target.id;
                navLookup.forEach((btn, id) => {
                    btn.classList.toggle('active', id === sectionId);
                });
            }
        },
        { threshold: 0.35 }
    );

    sections.forEach((section) => observer.observe(section));
}

function initialiseResultPanels() {
    const placeholders = {
        'parser-results': 'Run a parser request to inspect Docs operations.',
        'docx-results': 'Upload a DOCX file to extract text.',
        'image-results': 'Generate a glow or before/after clip to preview the output.',
        'js-results': 'Split a panorama or proxy a Cobalt download to inspect generated assets.',
        'media-results': 'Inspect a media URL with yt-dlp to reveal metadata, downloads, and subtitles.'
    };

    Object.entries(placeholders).forEach(([id, message]) => {
        const container = document.getElementById(id);
        if (container && !container.children.length) {
            const paragraph = document.createElement('p');
            paragraph.textContent = message;
            container.appendChild(paragraph);
        }
    });
}

function setupHalationsControls() {
    const blurSlider = document.getElementById('blur-slider');
    const blurValue = document.getElementById('blur-value');
    const brightnessSlider = document.getElementById('brightness-slider');
    const brightnessValue = document.getElementById('brightness-value');
    const strengthSlider = document.getElementById('strength-slider');
    const strengthValue = document.getElementById('strength-value');

    if (blurSlider && blurValue) {
        blurValue.textContent = blurSlider.value;
        blurSlider.addEventListener('input', () => {
            blurValue.textContent = blurSlider.value;
        });
    }

    if (brightnessSlider && brightnessValue) {
        brightnessValue.textContent = brightnessSlider.value;
        brightnessSlider.addEventListener('input', () => {
            brightnessValue.textContent = brightnessSlider.value;
        });
    }

    if (strengthSlider && strengthValue) {
        strengthValue.textContent = strengthSlider.value;
        strengthSlider.addEventListener('input', () => {
            strengthValue.textContent = strengthSlider.value;
        });
    }
}

function setupBeforeAfterControls() {
    const toggle = document.getElementById('before-after-text-toggle');
    const textarea = document.getElementById('before-after-text');
    if (!toggle || !textarea) {
        return;
    }

    toggle.addEventListener('change', () => {
        textarea.style.display = toggle.checked ? 'block' : 'none';
    });
}

function setupForms() {
    setupParserForms();
    setupDocxForm();
    setupHalationsForm();
    setupBeforeAfterForm();
    setupPanosplitterForm();
    setupCobaltControls();
    setupCobaltForm();
    setupYtDlpForm();
}

function setupParserForms() {
    attachSubmit('html-parse-form', async (form) => {
        const html = form.querySelector('textarea[name="html"]').value.trim();
        if (!html) {
            throw new Error('Provide HTML to parse.');
        }
        const result = await postJSON('/parse/html', { html });
        setResult('parser-results', [
            createResultGroup('HTML → Requests', [createPre(result.requests)])
        ]);
        showToast('HTML parsed successfully.');
    });

    attachSubmit('markdown-parse-form', async (form) => {
        const markdown = form.querySelector('textarea[name="markdown"]').value.trim();
        if (!markdown) {
            throw new Error('Provide Markdown to parse.');
        }
        const result = await postJSON('/parse/markdown', { markdown });
        setResult('parser-results', [
            createResultGroup('Markdown → Requests', [createPre(result.requests)])
        ]);
        showToast('Markdown parsed successfully.');
    });

    attachSubmit('docs-html-form', async (form) => {
        const html = form.querySelector('textarea[name="html"]').value.trim();
        if (!html) {
            throw new Error('Provide HTML to convert.');
        }
        const result = await postJSON('/parse/docs/html', { html });
        setResult('parser-results', [
            createResultGroup('Docs BatchUpdate (HTML)', [createPre(result.requests)])
        ]);
        showToast('Docs requests generated from HTML.');
    });

    attachSubmit('docs-markdown-form', async (form) => {
        const markdown = form.querySelector('textarea[name="markdown"]').value.trim();
        if (!markdown) {
            throw new Error('Provide Markdown to convert.');
        }
        const result = await postJSON('/parse/docs/markdown', { markdown });
        setResult('parser-results', [
            createResultGroup('Docs BatchUpdate (Markdown)', [createPre(result.requests)])
        ]);
        showToast('Docs requests generated from Markdown.');
    });
}

function setupDocxForm() {
    attachSubmit('docx-parse-form', async (form) => {
        const fileInput = document.getElementById('docx-file');
        const file = fileInput && fileInput.files ? fileInput.files[0] : null;
        if (!file) {
            throw new Error('Select a DOCX file first.');
        }

        const response = await fetch('/docx/parse', {
            method: 'POST',
            headers: {
                'Content-Type': file.type || 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            },
            body: file
        });
        const result = await parseResponse(response);
        setResult('docx-results', [
            createResultGroup('Extracted Text', [createPre(result.text || '')]),
            createResultGroup('Metadata', [createMetaGrid({
                'File name': file.name,
                'Content type': result.content_type,
                'Size (bytes)': result.size_bytes
            })])
        ]);
        showToast('DOCX parsed successfully.');
    });
}

function setupHalationsForm() {
    attachSubmit('halations-form', async () => {
        const imageInput = document.getElementById('halations-image');
        const file = imageInput && imageInput.files ? imageInput.files[0] : null;
        if (!file) {
            throw new Error('Choose an image to apply the glow.');
        }

        const formData = new FormData();
        formData.append('image', file);
        formData.append('blur_amount', document.getElementById('blur-slider').value);
        formData.append('brightness_threshold', document.getElementById('brightness-slider').value);
        formData.append('strength', document.getElementById('strength-slider').value);

        const response = await fetch('/image-tools/halations?response_format=json', {
            method: 'POST',
            body: formData
        });
        const result = await parseResponse(response);

        const image = new Image();
        image.src = `data:${result.content_type};base64,${result.image_base64}`;
        image.alt = 'Halations glow result';

        const download = createDownloadLinkFromBase64(
            result.image_base64,
            result.content_type,
            result.filename,
            'Download JPEG'
        );

        const nodes = [image, download];
        if (result.message) {
            nodes.push(createNotice(result.message));
        }
        nodes.push(createMetaGrid(result.metadata));

        setResult('image-results', [createResultGroup('Halations Glow Result', nodes)]);
        showToast('Halations glow applied.');
    });
}

function setupBeforeAfterForm() {
    attachSubmit('before-after-form', async () => {
        const beforeInput = document.getElementById('before-image');
        const afterInput = document.getElementById('after-image');
        const beforeFile = beforeInput && beforeInput.files ? beforeInput.files[0] : null;
        const afterFile = afterInput && afterInput.files ? afterInput.files[0] : null;
        if (!beforeFile || !afterFile) {
            throw new Error('Select both before and after images.');
        }

        const formData = new FormData();
        formData.append('before_image', beforeFile);
        formData.append('after_image', afterFile);
        formData.append('duration_seconds', document.getElementById('before-after-duration').value || '6');
        formData.append('fps', document.getElementById('before-after-fps').value || '30');
        formData.append('cycles', document.getElementById('before-after-cycles').value || '2');
        formData.append('line_thickness', document.getElementById('before-after-line').value || '6');

        const textToggle = document.getElementById('before-after-text-toggle');
        const overlayText = document.getElementById('before-after-text');
        if (textToggle && textToggle.checked) {
            formData.append('add_text', 'true');
            if (overlayText && overlayText.value.trim()) {
                formData.append('overlay_text', overlayText.value.trim());
            }
        } else {
            formData.append('add_text', 'false');
        }

        const response = await fetch('/image-tools/before-after?response_format=json', {
            method: 'POST',
            body: formData
        });
        const result = await parseResponse(response);

        const video = createVideoFromBase64(result.video_base64, result.content_type, {
            controls: true
        });

        const download = createDownloadLinkFromBase64(
            result.video_base64,
            result.content_type,
            result.filename,
            'Download MP4'
        );

        const elements = [];
        if (video) {
            elements.push(video);
        }
        elements.push(download);
        if (result.message) {
            elements.push(createNotice(result.message));
        }
        elements.push(createMetaGrid(result.metadata));

        setResult('image-results', [createResultGroup('Before/After Clip', elements)]);
        showToast('Before/after animation generated.');
    });
}

function setupPanosplitterForm() {
    attachSubmit('panosplitter-form', async () => {
        const imageInput = document.getElementById('panosplitter-image');
        const file = imageInput && imageInput.files ? imageInput.files[0] : null;
        if (!file) {
            throw new Error('Upload a panorama image first.');
        }

        const formData = new FormData();
        formData.append('image', file);
        const highResCheckbox = document.getElementById('panosplitter-highres');
        formData.append('high_res', highResCheckbox && highResCheckbox.checked ? 'true' : 'false');

        const response = await fetch('/js-tools/panosplitter?response_format=json', {
            method: 'POST',
            body: formData
        });
        const result = await parseResponse(response);

        const preview = createImageFromBase64(
            result.full_view && result.full_view.base64,
            result.full_view && result.full_view.content_type,
            'Panosplitter preview'
        );

        const slicesGrid = document.createElement('div');
        slicesGrid.className = 'slice-grid';
        (result.slices || []).slice(0, 8).forEach((slice, index) => {
            const img = createImageFromBase64(
                slice && slice.base64,
                slice && slice.content_type,
                `Slice ${index + 1}`
            );
            if (img) {
                slicesGrid.appendChild(img);
            }
        });

        const download = createDownloadLinkFromBase64(
            result.zip_file.base64,
            result.zip_file.content_type,
            result.zip_file.filename,
            'Download Zip'
        );

        const elements = [];
        if (preview) {
            elements.push(preview);
        }
        elements.push(slicesGrid, download);
        elements.push(createMetaGrid(result.metadata));
        if (result.manifest) {
            elements.push(createPre(result.manifest));
        }

        setResult('js-results', [createResultGroup('Panosplitter Output', elements)]);
        showToast('Panorama split successfully.');
    });
}

function setupCobaltControls() {
    updateCobaltStatusBanner();
    setupCobaltShortcuts();

    const presetSelect = document.getElementById('cobalt-preset');
    if (presetSelect) {
        presetSelect.addEventListener('change', () => {
            applyCobaltPreset(presetSelect);
            updateCobaltPresetDescription(presetSelect);
        });
        updateCobaltPresetDescription(presetSelect);
    }

    const customOptionsContainer = document.getElementById('cobalt-custom-options');
    if (customOptionsContainer) {
        customOptionsContainer.addEventListener('click', (event) => {
            const target = event.target;
            if (target instanceof HTMLElement && target.hasAttribute('data-option-remove')) {
                const row = target.closest('.cobalt-option-row');
                if (row) {
                    row.remove();
                }
            }
        });

        customOptionsContainer.addEventListener('change', (event) => {
            const target = event.target;
            if (target instanceof HTMLSelectElement && target.hasAttribute('data-option-type')) {
                setCobaltOptionPlaceholder(target);
            }
        });
    }

    if (customOptionsContainer && !customOptionsContainer.querySelector('.cobalt-option-row')) {
        addCobaltOptionRow();
    }

    const addOptionButton = document.getElementById('cobalt-add-option');
    if (addOptionButton) {
        addOptionButton.addEventListener('click', () => addCobaltOptionRow());
    }
}

function updateCobaltStatusBanner() {
    const banner = document.getElementById('cobalt-status-banner');
    if (!banner) {
        return;
    }

    const cobaltConfig = config.cobalt || {};
    const messageNode = banner.querySelector('.status-banner__message');
    const quickActions = document.getElementById('cobalt-quick-actions');

    banner.classList.remove(
        'status-banner--success',
        'status-banner--info',
        'status-banner--warning',
        'status-banner--danger'
    );

    if (!cobaltConfig.configured) {
        if (messageNode) {
            messageNode.textContent =
                'Cobalt is disabled. Set COBALT_API_BASE_URL or remove it to enable the built-in fallback instance.';
        }
        banner.classList.add('status-banner--danger');
        banner.hidden = false;
        disableCobaltFormInputs();
        if (quickActions) {
            quickActions.classList.add('quick-actions--disabled');
            quickActions.querySelectorAll('button').forEach((button) => {
                button.disabled = true;
            });
        }
        return;
    }

    const label = cobaltConfig.display_name || cobaltConfig.base_url;
    if (messageNode) {
        messageNode.textContent = cobaltConfig.usingFallback
            ? `Using public fallback (${label}). Configure COBALT_API_BASE_URL for a private instance.`
            : `Connected to ${label}.`;
    }

    banner.classList.add(cobaltConfig.usingFallback ? 'status-banner--info' : 'status-banner--success');
    banner.hidden = false;

    if (quickActions) {
        quickActions.classList.remove('quick-actions--disabled');
        quickActions.querySelectorAll('button').forEach((button) => {
            button.disabled = false;
        });
    }
}

function disableCobaltFormInputs() {
    const form = document.getElementById('cobalt-form');
    if (!form) {
        return;
    }

    form.classList.add('is-disabled');
    form.querySelectorAll('input, select, textarea, button').forEach((element) => {
        element.disabled = true;
    });
}

function setupCobaltShortcuts() {
    const container = document.getElementById('cobalt-quick-actions');
    if (!container) {
        return;
    }

    const cobaltConfig = config.cobalt || {};
    const urlField = document.getElementById('cobalt-url');
    const buttons = container.querySelectorAll('[data-shortcut]');

    if (!cobaltConfig.configured) {
        buttons.forEach((button) => {
            button.disabled = true;
        });
        return;
    }

    buttons.forEach((button) => {
        button.addEventListener('click', async () => {
            if (!(urlField instanceof HTMLInputElement)) {
                return;
            }

            const shortcut = button.dataset.shortcut;
            if (!shortcut) {
                return;
            }

            const url = urlField.value.trim();
            if (!url) {
                showToast('Paste a URL before choosing a shortcut.', 'warning');
                urlField.focus();
                return;
            }

            const labelNode = button.querySelector('.quick-action-btn__label');
            const label = labelNode ? labelNode.textContent.trim() : shortcut;
            const responseFormat = button.dataset.responseFormat || 'json';

            try {
                await withButtonLoading(button, async () => {
                    const payload = { url };
                    if (responseFormat) {
                        payload.response_format = responseFormat;
                    }

                    const response = await fetch(`/js-tools/cobalt/shortcuts/${shortcut}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    });

                    if (responseFormat === 'binary') {
                        await renderCobaltBinaryResponse(response, {
                            fallbackFilename: `${shortcut}.bin`,
                            successMessage: `${label} ready.`,
                        });
                        return;
                    }

                    await renderCobaltJsonResponse(response, {
                        title: `${label} (Shortcut)`,
                        successMessage: `${label} response ready.`,
                    });
                });
            } catch (error) {
                console.error(error);
                showToast(error.message || 'Cobalt shortcut failed.', 'error');
            }
        });
    });
}

function applyCobaltPreset(select) {
    if (!(select instanceof HTMLSelectElement)) {
        return;
    }

    const option = select.selectedOptions[0];
    if (!option) {
        return;
    }

    const shouldReset = option.dataset.reset !== 'false';
    let presetValues = {};

    if (shouldReset) {
        resetCobaltPresetFields();
    }

    if (option.dataset.options) {
        try {
            presetValues = JSON.parse(option.dataset.options);
        } catch (error) {
            console.warn('Invalid preset configuration for Cobalt option', error);
        }
    }

    const binaryToggle = document.getElementById('cobalt-binary');
    const filenameField = document.getElementById('cobalt-filename');

    Object.entries(presetValues).forEach(([key, value]) => {
        if (key === 'response_format' && binaryToggle instanceof HTMLInputElement) {
            binaryToggle.checked = String(value).toLowerCase() === 'binary';
            return;
        }

        if (key === 'download_filename' && filenameField instanceof HTMLInputElement) {
            filenameField.value = String(value);
            return;
        }

        if (Object.prototype.hasOwnProperty.call(COBALT_FIELD_IDS, key)) {
            const fieldId = COBALT_FIELD_IDS[key];
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
                field.value = String(value);
            }
            return;
        }

        if (Object.prototype.hasOwnProperty.call(COBALT_BOOLEAN_FIELDS, key)) {
            const fieldId = COBALT_BOOLEAN_FIELDS[key];
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLInputElement) {
                field.checked = Boolean(value);
            }
            return;
        }

        if (Object.prototype.hasOwnProperty.call(COBALT_BOOLEAN_SELECT_FIELDS, key)) {
            const fieldId = COBALT_BOOLEAN_SELECT_FIELDS[key];
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLSelectElement) {
                if (value === true || value === 'true') {
                    field.value = 'true';
                } else if (value === false || value === 'false') {
                    field.value = 'false';
                } else {
                    field.value = '';
                }
            }
        }
    });
}

function resetCobaltPresetFields() {
    Object.values(COBALT_FIELD_IDS).forEach((fieldId) => {
        const field = document.getElementById(fieldId);
        if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
            field.value = '';
        }
    });

    Object.values(COBALT_BOOLEAN_FIELDS).forEach((fieldId) => {
        const field = document.getElementById(fieldId);
        if (field instanceof HTMLInputElement) {
            field.checked = false;
        }
    });

    Object.values(COBALT_BOOLEAN_SELECT_FIELDS).forEach((fieldId) => {
        const field = document.getElementById(fieldId);
        if (field instanceof HTMLSelectElement) {
            field.value = '';
        }
    });

    const binaryToggle = document.getElementById('cobalt-binary');
    if (binaryToggle instanceof HTMLInputElement) {
        binaryToggle.checked = false;
    }

    const filenameField = document.getElementById('cobalt-filename');
    if (filenameField instanceof HTMLInputElement) {
        filenameField.value = '';
    }
}

function updateCobaltPresetDescription(select) {
    const description = document.getElementById('cobalt-preset-description');
    if (!(select instanceof HTMLSelectElement) || !description) {
        return;
    }

    const option = select.selectedOptions[0];
    if (option && option.dataset.description) {
        description.textContent = option.dataset.description;
        description.hidden = false;
    } else {
        description.textContent = '';
        description.hidden = true;
    }
}

function addCobaltOptionRow(key = '', value = '', type = 'string') {
    const container = document.getElementById('cobalt-custom-options');
    const template = document.getElementById('cobalt-option-template');
    if (!container || !(template instanceof HTMLTemplateElement)) {
        return;
    }

    const clone = template.content.firstElementChild.cloneNode(true);
    const keyInput = clone.querySelector('[data-option-key]');
    const valueInput = clone.querySelector('[data-option-value]');
    const typeSelect = clone.querySelector('[data-option-type]');

    if (keyInput instanceof HTMLInputElement) {
        keyInput.value = key;
    }
    if (valueInput instanceof HTMLInputElement) {
        valueInput.value = value;
    }
    if (typeSelect instanceof HTMLSelectElement) {
        if (Array.from(typeSelect.options).some((optionEl) => optionEl.value === type)) {
            typeSelect.value = type;
        }
        setCobaltOptionPlaceholder(typeSelect);
    }

    container.appendChild(clone);
}

function setCobaltOptionPlaceholder(typeSelect) {
    const row = typeSelect.closest('.cobalt-option-row');
    if (!row) {
        return;
    }
    const valueInput = row.querySelector('[data-option-value]');
    if (!(valueInput instanceof HTMLInputElement)) {
        return;
    }

    const placeholders = {
        string: 'value',
        number: '123',
        boolean: 'true / false',
        json: '{"key":"value"}'
    };

    valueInput.placeholder = placeholders[typeSelect.value] || 'value';
}

function collectCobaltCustomOptions() {
    const container = document.getElementById('cobalt-custom-options');
    if (!container) {
        return {};
    }

    const options = {};
    const rows = container.querySelectorAll('.cobalt-option-row');

    rows.forEach((row) => {
        const keyInput = row.querySelector('[data-option-key]');
        const valueInput = row.querySelector('[data-option-value]');
        const typeSelect = row.querySelector('[data-option-type]');

        const key = keyInput instanceof HTMLInputElement ? keyInput.value.trim() : '';
        const rawValue = valueInput instanceof HTMLInputElement ? valueInput.value.trim() : '';
        const type = typeSelect instanceof HTMLSelectElement ? typeSelect.value : 'string';

        if (!key && !rawValue) {
            return;
        }

        if (!key) {
            throw new Error('Provide a key for each custom option.');
        }

        if (!rawValue) {
            throw new Error(`Provide a value for the custom option "${key}".`);
        }

        try {
            options[key] = transformCobaltCustomOptionValue(type, rawValue);
        } catch (error) {
            if (error instanceof SyntaxError && type === 'json') {
                throw new Error(`Custom option "${key}" must be valid JSON.`);
            }
            if (error instanceof TypeError) {
                if (error.message === 'number') {
                    throw new Error(`Custom option "${key}" must be a valid number.`);
                }
                if (error.message === 'boolean') {
                    throw new Error(`Custom option "${key}" must be 'true' or 'false'.`);
                }
            }
            throw new Error(`Unable to parse the value for custom option "${key}".`);
        }
    });

    return options;
}

function transformCobaltCustomOptionValue(type, rawValue) {
    if (type === 'number') {
        const parsed = Number(rawValue);
        if (Number.isNaN(parsed)) {
            throw new TypeError('number');
        }
        return parsed;
    }

    if (type === 'boolean') {
        const normalized = rawValue.toLowerCase();
        if (['true', '1', 'yes', 'on'].includes(normalized)) {
            return true;
        }
        if (['false', '0', 'no', 'off'].includes(normalized)) {
            return false;
        }
        throw new TypeError('boolean');
    }

    if (type === 'json') {
        return JSON.parse(rawValue);
    }

    return rawValue;
}

async function renderCobaltBinaryResponse(response, options = {}) {
    const blob = await parseBinaryResponse(response);
    const disposition = response.headers.get('Content-Disposition');
    const metadataHeader = response.headers.get('X-Cobalt-Metadata');

    const metadata = metadataHeader ? safeJsonDecode(atob(metadataHeader)) : null;
    const filename =
        options.downloadFilename ||
        parseFilename(disposition) ||
        options.fallbackFilename ||
        'cobalt-download.bin';

    const groups = [
        createResultGroup(options.title || 'Cobalt Download', [
            createDownloadLinkFromBlob(blob, filename, options.linkLabel || 'Download Media')
        ])
    ];

    if (metadata) {
        groups.push(createResultGroup('Cobalt Metadata', [createPre(metadata)]));
        groups.push(...buildSubtitleGroups(metadata));
    }

    setResult(options.containerId || 'js-results', groups);
    showToast(options.successMessage || 'Cobalt download ready.');

    return { blob, metadata, filename };
}

async function renderCobaltJsonResponse(response, options = {}) {
    const payload = await parseResponse(response);
    const containerId = options.containerId || 'js-results';
    const title = options.title || 'Cobalt Response';
    const groups = [createResultGroup(title, [createPre(payload)])];

    const shouldIncludeSubtitles = options.includeSubtitles !== false;
    if (shouldIncludeSubtitles && payload && typeof payload === 'object') {
        const subtitleSource = payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : payload;
        const subtitleGroups = buildSubtitleGroups(subtitleSource);
        if (subtitleGroups.length) {
            groups.push(...subtitleGroups);
        }
    }

    setResult(containerId, groups);
    showToast(options.successMessage || 'Cobalt response received.');

    return payload;
}

function setupCobaltForm() {
    if (config.cobalt && config.cobalt.configured === false) {
        return;
    }

    attachSubmit('cobalt-form', async () => {
        const urlField = document.getElementById('cobalt-url');
        const binaryToggle = document.getElementById('cobalt-binary');
        const filenameField = document.getElementById('cobalt-filename');
        const payloadField = document.getElementById('cobalt-payload');

        const urlValue = urlField.value.trim();
        if (!urlValue) {
            throw new Error('Provide a URL to send to Cobalt.');
        }

        const rawPayload = payloadField.value.trim();
        let extraPayload = {};
        if (rawPayload) {
            try {
                extraPayload = JSON.parse(rawPayload);
            } catch (error) {
                throw new Error('Raw Cobalt payload must be valid JSON.');
            }
            if (!extraPayload || typeof extraPayload !== 'object' || Array.isArray(extraPayload)) {
                throw new Error('Raw Cobalt payload must be a JSON object.');
            }
        }

        const customOptions = collectCobaltCustomOptions();

        const payload = {
            url: urlValue,
            response_format: binaryToggle.checked ? 'binary' : 'json'
        };

        const filenameOverride = filenameField.value.trim();
        if (filenameOverride) {
            payload.download_filename = filenameOverride;
        }

        Object.entries(COBALT_FIELD_IDS).forEach(([key, fieldId]) => {
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
                const value = field.value.trim();
                if (value) {
                    payload[key] = value;
                }
            }
        });

        Object.entries(COBALT_BOOLEAN_FIELDS).forEach(([key, fieldId]) => {
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLInputElement && field.checked) {
                payload[key] = true;
            }
        });

        Object.entries(COBALT_BOOLEAN_SELECT_FIELDS).forEach(([key, fieldId]) => {
            const field = document.getElementById(fieldId);
            if (field instanceof HTMLSelectElement) {
                if (field.value === 'true') {
                    payload[key] = true;
                } else if (field.value === 'false') {
                    payload[key] = false;
                }
            }
        });

        if (customOptions && Object.keys(customOptions).length) {
            Object.assign(payload, customOptions);
        }

        if (extraPayload && Object.keys(extraPayload).length) {
            Object.assign(payload, extraPayload);
        }

        const response = await fetch('/js-tools/cobalt', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (binaryToggle.checked) {
            await renderCobaltBinaryResponse(response, {
                downloadFilename: filenameOverride,
            });
        } else {
            await renderCobaltJsonResponse(response);
        }
    });
}

function setupYtDlpForm() {
    const form = document.getElementById('yt-dlp-form');
    if (!form) {
        return;
    }

    const urlField = document.getElementById('yt-dlp-url');
    const formatField = document.getElementById('yt-dlp-format');
    const playlistItemsField = document.getElementById('yt-dlp-playlist-items');
    const filenameField = document.getElementById('yt-dlp-filename');
    const headersField = document.getElementById('yt-dlp-headers');
    const proxyField = document.getElementById('yt-dlp-proxy');
    const writeSubtitlesToggle = document.getElementById('yt-dlp-write-subtitles');
    const writeAutoSubToggle = document.getElementById('yt-dlp-write-auto-sub');
    const subtitleLangsField = document.getElementById('yt-dlp-subtitle-langs');
    const templateSelect = document.getElementById('yt-dlp-template');
    const templateHint = document.getElementById('yt-dlp-template-hint');
    const openModalButton = document.getElementById('yt-dlp-open-modal');
    const modal = document.getElementById('yt-dlp-modal');
    const modalSubtitle = document.getElementById('yt-dlp-modal-subtitle');
    const qualityList = document.getElementById('yt-dlp-quality-list');
    const modalDownloadButton = document.getElementById('yt-dlp-modal-download');
    const modalCloseButton = document.getElementById('yt-dlp-modal-close');

    ytDlpState.dom = {
        form,
        urlField,
        formatField,
        playlistItemsField,
        filenameField,
        headersField,
        proxyField,
        writeSubtitlesToggle,
        writeAutoSubToggle,
        subtitleLangsField,
        templateSelect,
        templateHint,
        openModalButton,
        modal,
        modalSubtitle,
        qualityList,
        modalDownloadButton
    };

    const templatePresets = {
        best: {
            description: 'Ideal when you want the highest quality video with audio.',
            values: {
                format: 'bestvideo*+bestaudio/best',
                writeSubtitles: false,
                writeAutoSub: false,
                subtitleLangs: ''
            }
        },
        hd1080: {
            description: 'Prefer 1080p (or the best available below it) with merged audio.',
            values: {
                format: 'bv*[height<=1080]+ba/b[height<=1080]',
                writeSubtitles: false,
                writeAutoSub: false
            }
        },
        audio: {
            description: 'Grab the best available audio track without video.',
            values: {
                format: 'bestaudio/best',
                writeSubtitles: false,
                writeAutoSub: false
            }
        },
        subtitles: {
            description: 'Download metadata while preparing subtitle files for offline viewing.',
            values: {
                format: 'best',
                writeSubtitles: true,
                writeAutoSub: true
            }
        },
        custom: {
            description: 'Keep full control of every yt-dlp option yourself.'
        }
    };

    function applyTemplateChoice(id, applyValues = true) {
        const preset = templatePresets[id] || templatePresets.best;
        ytDlpState.lastTemplate = id;
        if (templateHint) {
            templateHint.textContent = preset.description;
        }
        if (!applyValues || !preset.values) {
            return;
        }
        const values = preset.values;
        if (formatField && Object.prototype.hasOwnProperty.call(values, 'format')) {
            formatField.value = values.format || '';
        }
        if (writeSubtitlesToggle && Object.prototype.hasOwnProperty.call(values, 'writeSubtitles')) {
            writeSubtitlesToggle.checked = Boolean(values.writeSubtitles);
        }
        if (writeAutoSubToggle && Object.prototype.hasOwnProperty.call(values, 'writeAutoSub')) {
            writeAutoSubToggle.checked = Boolean(values.writeAutoSub);
        }
        if (subtitleLangsField && Object.prototype.hasOwnProperty.call(values, 'subtitleLangs')) {
            subtitleLangsField.value = values.subtitleLangs || '';
        }
    }

    if (templateSelect) {
        templateSelect.addEventListener('change', () => {
            applyTemplateChoice(templateSelect.value);
        });
        if (!templateSelect.value) {
            templateSelect.value = 'best';
        }
        applyTemplateChoice(templateSelect.value, true);
    }

    if (openModalButton) {
        openModalButton.disabled = true;
        openModalButton.addEventListener('click', () => openYtDlpModal());
    }

    if (modalCloseButton) {
        modalCloseButton.addEventListener('click', () => closeYtDlpModal());
    }
    if (modal) {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeYtDlpModal();
            }
        });
        modal.querySelectorAll('[data-modal-dismiss]').forEach((node) => {
            node.addEventListener('click', () => closeYtDlpModal());
        });
    }

    if (qualityList) {
        qualityList.addEventListener('change', (event) => {
            if (event.target && event.target.name === 'yt-dlp-quality') {
                updateYtDlpQualitySelection(event.target.value);
            }
        });
    }

    if (modalDownloadButton) {
        modalDownloadButton.addEventListener('click', () => {
            if (!qualityList) {
                return;
            }
            const selected = qualityList.querySelector('input[name="yt-dlp-quality"]:checked');
            if (!selected) {
                showToast('Choose a format to download first.', 'error');
                return;
            }
            handleYtDlpDownload(selected.value);
        });
    }

    attachSubmit('yt-dlp-form', async () => {
        const payload = buildYtDlpPayload('json');
        const response = await fetch('/media/yt-dlp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const result = await parseResponse(response);
        if (!result || !result.metadata) {
            throw new Error('yt-dlp did not return any metadata for this URL.');
        }
        ytDlpState.metadata = result.metadata;
        ytDlpState.rawResponse = result;
        renderYtDlpResults({ metadata: result.metadata, raw: result });
        setDownloadButtonsState(Array.isArray(result.metadata.formats) && result.metadata.formats.length > 0);
        showToast('Metadata retrieved successfully.');
    });
}

function buildYtDlpPayload(responseFormat, overrides = {}) {
    const dom = ytDlpState.dom || {};
    const urlField = dom.urlField;
    const urlValue = urlField && urlField.value ? urlField.value.trim() : '';
    if (!urlValue) {
        throw new Error('Provide a URL to inspect.');
    }

    const payload = {
        url: urlValue,
        response_format: responseFormat,
        options: {
            noplaylist: true
        }
    };

    if (responseFormat === 'binary' && dom.filenameField && dom.filenameField.value.trim()) {
        payload.filename = dom.filenameField.value.trim();
    }

    const formatOverride = overrides.formatOverride;
    const formatField = dom.formatField;
    const formatValue =
        typeof formatOverride === 'string' && formatOverride.trim().length
            ? formatOverride.trim()
            : formatField && formatField.value
                ? formatField.value.trim()
                : '';
    if (formatValue) {
        payload.options.format = formatValue;
    }

    if (dom.playlistItemsField && dom.playlistItemsField.value.trim()) {
        payload.options.playlist_items = dom.playlistItemsField.value.trim();
    }

    if (dom.headersField && dom.headersField.value.trim()) {
        try {
            const parsedHeaders = JSON.parse(dom.headersField.value.trim());
            if (!parsedHeaders || typeof parsedHeaders !== 'object' || Array.isArray(parsedHeaders)) {
                throw new Error();
            }
            payload.options.http_headers = parsedHeaders;
        } catch (error) {
            throw new Error('HTTP headers must be a valid JSON object.');
        }
    }

    if (dom.proxyField && dom.proxyField.value.trim()) {
        payload.options.proxy = dom.proxyField.value.trim();
    }

    if (dom.writeSubtitlesToggle && dom.writeSubtitlesToggle.checked) {
        payload.options.writesubtitles = true;
    }

    if (dom.writeAutoSubToggle && dom.writeAutoSubToggle.checked) {
        payload.options.writeautomaticsub = true;
    }

    if (dom.subtitleLangsField && dom.subtitleLangsField.value.trim()) {
        const languages = dom.subtitleLangsField.value
            .split(',')
            .map((item) => item.trim())
            .filter((item) => item.length);
        if (languages.length) {
            payload.options.subtitleslangs = languages;
        }
    }

    if (overrides.options && typeof overrides.options === 'object') {
        payload.options = { ...payload.options, ...overrides.options };
    }

    return payload;
}

function renderYtDlpResults({ metadata, raw, download } = {}) {
    if (!metadata) {
        setResult('media-results', []);
        setDownloadButtonsState(false);
        return;
    }

    const hasFormats = Array.isArray(metadata.formats) && metadata.formats.length > 0;
    const groups = [];
    const summaryNodes = [];

    const summaryMeta = {};
    if (metadata.title) {
        summaryMeta.Title = metadata.title;
    }
    if (metadata.uploader || metadata.channel) {
        summaryMeta.Creator = metadata.uploader || metadata.channel;
    }
    if (Number.isFinite(metadata.duration)) {
        const formattedDuration = formatDuration(metadata.duration);
        if (formattedDuration) {
            summaryMeta.Duration = formattedDuration;
        }
    }
    if (metadata.view_count != null) {
        summaryMeta.Views = formatInteger(metadata.view_count);
    }
    if (metadata.upload_date) {
        const uploaded = formatUploadDate(metadata.upload_date);
        if (uploaded) {
            summaryMeta.Uploaded = uploaded;
        }
    }

    if (Object.keys(summaryMeta).length) {
        summaryNodes.push(createMetaGrid(summaryMeta));
    }

    if (metadata.thumbnail) {
        const thumbnail = document.createElement('img');
        thumbnail.src = metadata.thumbnail;
        thumbnail.alt = metadata.title ? `${metadata.title} thumbnail` : 'Media thumbnail';
        summaryNodes.push(thumbnail);
    }

    const actions = document.createElement('div');
    actions.className = 'yt-dlp-actions';
    const chooseButton = document.createElement('button');
    chooseButton.type = 'button';
    chooseButton.className = 'secondary-btn';
    chooseButton.textContent = 'Choose download quality';
    chooseButton.disabled = !hasFormats;
    chooseButton.addEventListener('click', () => openYtDlpModal());
    actions.appendChild(chooseButton);

    const helper = document.createElement('p');
    helper.className = 'helper-text';
    helper.textContent = hasFormats
        ? 'Pick a quality to download or try a different recipe from the dropdown above.'
        : 'No downloadable formats were reported, but raw metadata is available below.';
    actions.appendChild(helper);

    summaryNodes.push(actions);

    groups.push(createResultGroup('Media overview', summaryNodes));

    if (download && download.length) {
        groups.push(createResultGroup('Your download', download));
    }

    const rawPayload = raw && raw.metadata ? raw.metadata : raw;
    if (rawPayload) {
        groups.push(createResultGroup('Raw metadata', [createPre(rawPayload)]));
    }

    const subtitleGroups = buildSubtitleGroups(metadata);
    if (subtitleGroups.length) {
        groups.push(...subtitleGroups);
    }

    setResult('media-results', groups);
    setDownloadButtonsState(hasFormats);
}

function setDownloadButtonsState(enabled) {
    const dom = ytDlpState.dom || {};
    if (dom.openModalButton) {
        dom.openModalButton.disabled = !enabled;
    }
}

function openYtDlpModal() {
    const dom = ytDlpState.dom || {};
    const modal = dom.modal;
    if (!modal) {
        return;
    }
    if (!ytDlpState.metadata || !Array.isArray(ytDlpState.metadata.formats) || !ytDlpState.metadata.formats.length) {
        showToast('Fetch media info before choosing a download.', 'error');
        return;
    }

    populateYtDlpModal(ytDlpState.metadata.formats);

    if (dom.modalSubtitle) {
        dom.modalSubtitle.textContent = ytDlpState.metadata.title || '';
    }

    modal.hidden = false;
    document.body.classList.add('modal-open');

    const dialog = modal.querySelector('.modal__dialog');
    if (dialog) {
        dialog.setAttribute('tabindex', '-1');
        dialog.focus();
    }

    if (!ytDlpState.modalKeyListener) {
        ytDlpState.modalKeyListener = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeYtDlpModal();
            }
        };
        document.addEventListener('keydown', ytDlpState.modalKeyListener);
    }
}

function closeYtDlpModal() {
    const dom = ytDlpState.dom || {};
    const modal = dom.modal;
    if (!modal || modal.hidden) {
        return;
    }
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    if (ytDlpState.modalKeyListener) {
        document.removeEventListener('keydown', ytDlpState.modalKeyListener);
        ytDlpState.modalKeyListener = null;
    }
}

function populateYtDlpModal(formats) {
    const dom = ytDlpState.dom || {};
    const qualityList = dom.qualityList;
    const downloadButton = dom.modalDownloadButton;
    if (!qualityList) {
        return;
    }

    qualityList.innerHTML = '';
    const options = normaliseYtDlpFormats(formats);
    ytDlpState.formatsById = new Map(options.map((option) => [option.id, option.original]));

    if (!options.length) {
        const empty = document.createElement('p');
        empty.className = 'quality-empty';
        empty.textContent = 'No downloadable formats were reported for this media.';
        qualityList.appendChild(empty);
        if (downloadButton) {
            downloadButton.disabled = true;
            downloadButton.textContent = downloadButton.dataset.originalLabel || 'Download selection';
        }
        return;
    }

    options.forEach((option, index) => {
        const label = document.createElement('label');
        label.className = 'quality-option';

        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'yt-dlp-quality';
        radio.value = option.id;
        radio.checked = index === 0;

        const content = document.createElement('div');
        const title = document.createElement('div');
        title.className = 'quality-title';
        title.textContent = option.label;
        content.appendChild(title);

        if (option.meta.length) {
            const meta = document.createElement('div');
            meta.className = 'quality-meta';
            option.meta.forEach((entry) => {
                const span = document.createElement('span');
                span.textContent = entry;
                meta.appendChild(span);
            });
            content.appendChild(meta);
        }

        label.append(radio, content);
        qualityList.appendChild(label);
    });

    const firstOption = options[0];
    if (firstOption) {
        updateYtDlpQualitySelection(firstOption.id);
        const firstRadio = qualityList.querySelector('input[name="yt-dlp-quality"]');
        if (firstRadio) {
            firstRadio.focus();
        }
    }
}

function normaliseYtDlpFormats(formats) {
    if (!Array.isArray(formats)) {
        return [];
    }

    const seen = new Set();

    const filtered = formats.filter((format) => {
        if (!format || typeof format !== 'object') {
            return false;
        }
        if (!format.format_id || seen.has(format.format_id)) {
            return false;
        }
        if (!isVideoFormat(format) && !isAudioFormat(format)) {
            return false;
        }
        seen.add(format.format_id);
        return true;
    });

    filtered.sort((a, b) => {
        const aVideo = isVideoFormat(a);
        const bVideo = isVideoFormat(b);
        if (aVideo !== bVideo) {
            return aVideo ? -1 : 1;
        }

        if (aVideo && bVideo) {
            const heightDelta = getFormatHeight(b) - getFormatHeight(a);
            if (heightDelta !== 0) {
                return heightDelta;
            }
            const fpsDelta = (b.fps || 0) - (a.fps || 0);
            if (fpsDelta !== 0) {
                return fpsDelta;
            }
        }

        const bitrateDelta = (b.tbr || b.abr || 0) - (a.tbr || a.abr || 0);
        if (bitrateDelta !== 0) {
            return bitrateDelta;
        }

        return 0;
    });

    return filtered.map((format) => ({
        id: format.format_id,
        label: buildYtDlpFormatLabel(format),
        meta: buildYtDlpFormatMeta(format),
        original: format
    }));
}

function updateYtDlpQualitySelection(formatId) {
    const dom = ytDlpState.dom || {};
    const qualityList = dom.qualityList;
    const downloadButton = dom.modalDownloadButton;
    if (!qualityList) {
        return;
    }

    const radios = qualityList.querySelectorAll('input[name="yt-dlp-quality"]');
    if (!formatId) {
        const checked = Array.from(radios).find((input) => input.checked);
        formatId = checked ? checked.value : null;
    }

    ytDlpState.selectedFormatId = formatId || null;

    qualityList.querySelectorAll('.quality-option').forEach((option) => {
        const radio = option.querySelector('input[name="yt-dlp-quality"]');
        option.classList.toggle('is-selected', Boolean(radio && radio.checked));
    });

    if (!downloadButton) {
        return;
    }

    if (!formatId || !ytDlpState.formatsById.has(formatId)) {
        downloadButton.disabled = true;
        downloadButton.textContent = downloadButton.dataset.originalLabel || 'Download selection';
        return;
    }

    if (!downloadButton.dataset.originalLabel) {
        downloadButton.dataset.originalLabel = downloadButton.textContent;
    }

    downloadButton.disabled = false;
    downloadButton.textContent = buildYtDlpDownloadLabel(ytDlpState.formatsById.get(formatId));
}

async function handleYtDlpDownload(formatId) {
    const dom = ytDlpState.dom || {};
    const downloadButton = dom.modalDownloadButton;
    if (!formatId) {
        return;
    }

    const originalLabel = downloadButton ? downloadButton.textContent : null;
    if (downloadButton) {
        downloadButton.disabled = true;
        downloadButton.textContent = 'Preparing download…';
    }

    try {
        if (!ytDlpState.formatsById.has(formatId)) {
            throw new Error('Select a valid format to download.');
        }
        const payload = buildYtDlpPayload('binary', { formatOverride: formatId });
        const response = await fetch('/media/yt-dlp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const blob = await parseBinaryResponse(response);
        const selectedFormat = ytDlpState.formatsById.get(formatId) || null;
        const filename =
            payload.filename ||
            parseFilename(response.headers.get('Content-Disposition')) ||
            buildFilenameFromMetadata(ytDlpState.metadata, selectedFormat);

        const downloadLink = createDownloadLinkFromBlob(blob, filename, 'Download media');
        const downloadNodes = [downloadLink];

        if (selectedFormat) {
            const downloadMeta = {};
            downloadMeta['Format ID'] = selectedFormat.format_id;
            if (selectedFormat.ext) {
                downloadMeta.Container = `.${selectedFormat.ext}`;
            }
            const qualityLabel = buildYtDlpFormatLabel(selectedFormat);
            if (qualityLabel) {
                downloadMeta.Quality = qualityLabel;
            }
            const reportedSize = selectedFormat.filesize || selectedFormat.filesize_approx;
            if (reportedSize) {
                downloadMeta['Reported size'] = formatBytes(reportedSize) || `${reportedSize} bytes`;
            }
            downloadNodes.push(createMetaGrid(downloadMeta));
        }

        closeYtDlpModal();
        renderYtDlpResults({ metadata: ytDlpState.metadata, raw: ytDlpState.rawResponse, download: downloadNodes });
        showToast('Media download ready.');
    } catch (error) {
        console.error(error);
        showToast(error.message || 'Download failed', 'error');
        return;
    } finally {
        if (downloadButton) {
            const fallback = downloadButton.dataset.originalLabel || originalLabel || 'Download selection';
            downloadButton.textContent = fallback;
            downloadButton.disabled = false;
        }
    }
}

function buildYtDlpFormatLabel(format) {
    if (!format) {
        return '';
    }
    const hasVideo = isVideoFormat(format);
    const hasAudio = isAudioFormat(format);
    const ext = format.ext ? `.${format.ext}` : '';

    if (hasVideo) {
        const height = getFormatHeight(format);
        const fps = format.fps ? `${Math.round(format.fps)}fps` : '';
        const resolution = height ? `${height}p` : format.format_note || 'Video';
        const descriptor = hasAudio ? 'video + audio' : 'video';
        const parts = [resolution];
        if (fps) {
            parts.push(fps);
        }
        parts.push(descriptor);
        if (ext) {
            parts.push(ext);
        }
        return parts.join(' ');
    }

    if (hasAudio) {
        const bitrate = format.abr || format.tbr;
        const parts = ['Audio'];
        if (bitrate) {
            parts.push(`${Math.round(bitrate)}kbps`);
        }
        if (ext) {
            parts.push(ext);
        }
        return parts.join(' ');
    }

    return format.format || format.format_id || 'Unknown format';
}

function buildYtDlpFormatMeta(format) {
    const entries = [];
    const seen = new Set();

    const height = getFormatHeight(format);
    if (height) {
        const resolutionLabel = format.width && format.height ? `${format.width}×${format.height}` : `${height}p`;
        entries.push(resolutionLabel);
    }

    if (format.fps) {
        entries.push(`${Math.round(format.fps)} fps`);
    }

    if (format.format_note) {
        entries.push(format.format_note);
    }

    if (format.ext) {
        entries.push(`.${format.ext}`);
    }

    if (isVideoFormat(format) && format.vcodec && format.vcodec !== 'none') {
        entries.push(format.vcodec);
    }

    if (isAudioFormat(format) && format.acodec && format.acodec !== 'none') {
        entries.push(format.acodec);
    }

    if (isAudioFormat(format)) {
        const bitrate = format.abr || format.tbr;
        if (bitrate) {
            entries.push(`${Math.round(bitrate)} kbps`);
        }
        if (format.asr) {
            entries.push(`${format.asr} Hz`);
        }
    }

    const size = format.filesize || format.filesize_approx;
    if (size) {
        entries.push(formatBytes(size) || `${size} bytes`);
    }

    entries.push(`Format ${format.format_id}`);

    return entries.filter((entry) => {
        if (!entry || seen.has(entry)) {
            return false;
        }
        seen.add(entry);
        return true;
    });
}

function buildYtDlpDownloadLabel(format) {
    if (!format) {
        return 'Download selection';
    }
    const parts = [];
    if (isVideoFormat(format) && getFormatHeight(format)) {
        parts.push(`${getFormatHeight(format)}p`);
    } else if (!isVideoFormat(format) && isAudioFormat(format)) {
        parts.push('audio');
    }
    if (format.ext) {
        parts.push(`.${format.ext}`);
    }
    if (!parts.length) {
        return 'Download selection';
    }
    return `Download ${parts.join(' ')}`;
}

function buildFilenameFromMetadata(metadata, format) {
    const ext = format && format.ext ? `.${format.ext}` : '.bin';
    const title = metadata && metadata.title ? metadata.title : 'download';
    const slug = title
        .toString()
        .trim()
        .replace(/\s+/g, '-')
        .replace(/[^a-zA-Z0-9-_]/g, '')
        .replace(/-{2,}/g, '-')
        .replace(/^-+|-+$/g, '');
    const safeTitle = slug || 'download';
    return safeTitle.endsWith(ext) ? safeTitle : `${safeTitle}${ext}`;
}

function getFormatHeight(format) {
    if (!format) {
        return 0;
    }
    if (typeof format.height === 'number') {
        return format.height;
    }
    if (typeof format.height === 'string' && format.height.trim()) {
        const parsed = Number.parseInt(format.height, 10);
        if (Number.isFinite(parsed)) {
            return parsed;
        }
    }
    const candidates = [format.resolution, format.format_note];
    for (const candidate of candidates) {
        if (typeof candidate !== 'string') {
            continue;
        }
        const match = candidate.match(/(\d{3,4})p/i);
        if (match) {
            const value = Number.parseInt(match[1], 10);
            if (Number.isFinite(value)) {
                return value;
            }
        }
    }
    return 0;
}

function isVideoFormat(format) {
    return Boolean(format && format.vcodec && format.vcodec !== 'none');
}

function isAudioFormat(format) {
    return Boolean(format && format.acodec && format.acodec !== 'none');
}

function formatDuration(totalSeconds) {
    if (!Number.isFinite(totalSeconds)) {
        return null;
    }
    const seconds = Math.max(0, Math.floor(totalSeconds));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatUploadDate(value) {
    if (typeof value !== 'string' || value.length !== 8) {
        return null;
    }
    const year = value.slice(0, 4);
    const month = value.slice(4, 6);
    const day = value.slice(6, 8);
    if (!year || !month || !day) {
        return null;
    }
    return `${year}-${month}-${day}`;
}

function formatInteger(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return String(value);
    }
    return number.toLocaleString();
}

function attachSubmit(formId, handler) {
    const form = document.getElementById(formId);
    if (!form) {
        return;
    }
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
            await withLoading(form, () => handler(form));
        } catch (error) {
            console.error(error);
            showToast(error.message || 'Request failed', 'error');
        }
    });
}

async function withLoading(form, callback) {
    const submit = form.querySelector('[type="submit"]');
    const originalText = submit ? submit.textContent : null;
    if (submit) {
        submit.disabled = true;
        submit.dataset.originalText = originalText || '';
        submit.textContent = 'Processing…';
    }

    try {
        return await callback();
    } finally {
        if (submit) {
            submit.disabled = false;
            submit.textContent = submit.dataset.originalText || originalText || 'Submit';
        }
    }
}

async function withButtonLoading(button, callback) {
    if (!(button instanceof HTMLButtonElement)) {
        return callback();
    }

    button.disabled = true;
    button.dataset.loading = 'true';

    try {
        return await callback();
    } finally {
        delete button.dataset.loading;
        button.disabled = false;
    }
}

async function postJSON(url, payload) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    });
    return parseResponse(response);
}

async function parseResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    const isJSON = contentType.includes('application/json');
    if (isJSON) {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(extractMessage(data, response.status));
        }
        return data;
    }

    const text = await response.text();
    if (!response.ok) {
        throw new Error(text || `Request failed (${response.status})`);
    }
    return text;
}

async function parseBinaryResponse(response) {
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed (${response.status})`);
    }
    return response.blob();
}

function extractMessage(payload, status) {
    if (!payload) {
        return `Request failed (${status})`;
    }
    if (typeof payload === 'string') {
        return payload;
    }
    if (typeof payload.detail === 'string') {
        return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
        return payload.detail.map((item) => item.msg || JSON.stringify(item)).join(', ');
    }
    return JSON.stringify(payload, null, 2);
}

function setResult(containerId, groups) {
    const container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    revokeObjectUrls(container);
    container.innerHTML = '';
    if (!groups || !groups.length) {
        const paragraph = document.createElement('p');
        paragraph.textContent = 'No output to display yet.';
        container.appendChild(paragraph);
        return;
    }
    groups.forEach((group) => container.appendChild(group));
}

function createResultGroup(title, nodes) {
    const wrapper = document.createElement('div');
    wrapper.className = 'result-group';
    if (title) {
        const heading = document.createElement('h4');
        heading.textContent = title;
        wrapper.appendChild(heading);
    }
    nodes.forEach((node) => {
        wrapper.appendChild(node);
    });
    return wrapper;
}

function createPre(data) {
    const pre = document.createElement('pre');
    if (typeof data === 'string') {
        pre.textContent = data;
    } else {
        pre.textContent = JSON.stringify(data, null, 2);
    }
    return pre;
}

function revokeObjectUrls(container) {
    if (!container) {
        return;
    }
    container.querySelectorAll('[data-object-url]').forEach((node) => {
        const url = node.getAttribute('data-object-url');
        if (url) {
            URL.revokeObjectURL(url);
        }
        node.removeAttribute('data-object-url');
    });
}

function createMetaGrid(meta) {
    const grid = document.createElement('div');
    grid.className = 'meta-grid';
    Object.entries(meta || {}).forEach(([key, value]) => {
        const item = document.createElement('div');
        item.className = 'meta-item';
        const label = document.createElement('span');
        label.className = 'label';
        label.textContent = key;
        const val = document.createElement('span');
        val.className = 'value';
        val.textContent = typeof value === 'object' ? JSON.stringify(value) : String(value);
        item.append(label, val);
        grid.appendChild(item);
    });
    return grid;
}

function buildSubtitleGroups(metadata) {
    if (!metadata || typeof metadata !== 'object') {
        return [];
    }

    const sections = [
        ['requested_subtitles', 'Requested Subtitles'],
        ['automatic_captions', 'Automatic Captions'],
        ['subtitles', 'Available Subtitles']
    ];

    return sections
        .map(([key, label]) => {
            const entries = metadata[key];
            if (!entries || typeof entries !== 'object' || Array.isArray(entries)) {
                return null;
            }
            const list = createSubtitleList(entries);
            if (!list) {
                return null;
            }
            return createResultGroup(label, [list]);
        })
        .filter(Boolean);
}

function createSubtitleList(entries) {
    const languages = Object.keys(entries || {});
    if (!languages.length) {
        return null;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'subtitle-list';

    languages.forEach((lang) => {
        const row = document.createElement('div');
        row.className = 'subtitle-row';

        const langBadge = document.createElement('span');
        langBadge.className = 'subtitle-lang';
        langBadge.textContent = lang;
        row.appendChild(langBadge);

        const details = document.createElement('div');
        details.className = 'subtitle-details';

        const value = entries[lang];
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            const metaParts = [];
            if (value.ext) {
                metaParts.push(`.${value.ext}`);
            }
            if (value.format) {
                metaParts.push(value.format);
            }
            if (value.filesize) {
                const formatted = formatBytes(value.filesize);
                metaParts.push(formatted ? `${formatted}` : `${value.filesize} bytes`);
            } else if (value.filesize_approx) {
                const formattedApprox = formatBytes(value.filesize_approx);
                metaParts.push(formattedApprox ? `≈${formattedApprox}` : `≈${value.filesize_approx} bytes`);
            }

            if (metaParts.length) {
                const meta = document.createElement('span');
                meta.textContent = metaParts.join(' · ');
                details.appendChild(meta);
            }

            if (value.url) {
                if (details.childNodes.length) {
                    details.appendChild(document.createTextNode(' '));
                }
                const link = document.createElement('a');
                link.href = value.url;
                link.target = '_blank';
                link.rel = 'noreferrer';
                link.textContent = 'Open URL';
                link.className = 'subtitle-link';
                details.appendChild(link);
            }

            if (!details.childNodes.length) {
                details.textContent = JSON.stringify(value);
            }
        } else if (value) {
            details.textContent = typeof value === 'string' ? value : JSON.stringify(value);
        } else {
            details.textContent = 'Unavailable';
        }

        row.appendChild(details);
        wrapper.appendChild(row);
    });

    return wrapper;
}

function formatBytes(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) {
        return null;
    }
    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
    let unitIndex = 0;
    let result = value;
    while (result >= 1024 && unitIndex < units.length - 1) {
        result /= 1024;
        unitIndex += 1;
    }
    const decimals = result >= 10 || unitIndex === 0 ? 0 : 1;
    return `${result.toFixed(decimals)} ${units[unitIndex]}`;
}

function createNotice(message) {
    const paragraph = document.createElement('p');
    paragraph.innerHTML = `<strong>Hint:</strong> ${escapeHtml(message)}`;
    return paragraph;
}

function escapeHtml(value) {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function base64ToBlob(base64, contentType) {
    const binary = window.atob(base64 || '');
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: contentType || 'application/octet-stream' });
}

function createObjectUrlFromBase64(base64, contentType) {
    const blob = base64ToBlob(base64, contentType);
    return URL.createObjectURL(blob);
}

function createImageFromBase64(base64, contentType, altText = '') {
    if (!base64) {
        return null;
    }
    const url = createObjectUrlFromBase64(base64, contentType || 'image/jpeg');
    const img = document.createElement('img');
    img.alt = altText || '';
    img.decoding = 'async';
    img.loading = 'lazy';
    img.src = url;
    img.dataset.objectUrl = url;
    return img;
}

function createVideoFromBase64(base64, contentType, options = {}) {
    if (!base64) {
        return null;
    }
    const url = createObjectUrlFromBase64(base64, contentType || 'video/mp4');
    const video = document.createElement('video');
    if (options.controls !== false) {
        video.controls = true;
    }
    if (options.autoplay) {
        video.autoplay = true;
        video.muted = true;
    }
    if (options.loop) {
        video.loop = true;
    }
    video.setAttribute('playsinline', '');
    video.src = url;
    video.dataset.objectUrl = url;
    return video;
}

function createDownloadLinkFromBase64(base64, contentType, filename, label) {
    const blob = base64ToBlob(base64, contentType);
    return createDownloadLinkFromBlob(blob, filename, label);
}

function createDownloadLinkFromBlob(blob, filename, label = 'Download') {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'download';
    link.className = 'download-link';
    link.textContent = label;
    link.dataset.objectUrl = url;
    link.addEventListener(
        'click',
        () => {
            setTimeout(() => {
                URL.revokeObjectURL(url);
                link.removeAttribute('data-object-url');
            }, 1000);
        },
        { once: true }
    );
    return link;
}

function parseFilename(disposition) {
    if (!disposition) {
        return null;
    }
    const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    if (utfMatch) {
        return decodeURIComponent(utfMatch[1]);
    }
    const quotedMatch = /filename="([^"\\]+)"/i.exec(disposition);
    if (quotedMatch) {
        return quotedMatch[1];
    }
    return null;
}

function safeJsonDecode(value) {
    try {
        return JSON.parse(value);
    } catch (error) {
        console.warn('Failed to decode JSON payload', error);
        return null;
    }
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) {
        return;
    }
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.hidden = false;
    if (toastState.timer) {
        window.clearTimeout(toastState.timer);
    }
    toastState.timer = window.setTimeout(() => {
        toast.hidden = true;
    }, 4000);
}

async function loadEndpointCatalogue() {
    const listContainer = document.getElementById('endpoint-list');
    const filterInput = document.getElementById('endpoint-filter');
    if (!listContainer) {
        return;
    }

    try {
        const response = await fetch(OPENAPI_URL, { headers: { Accept: 'application/json' } });
        const schema = await parseResponse(response);
        endpointCatalogue = buildEndpointGroups(schema);
        renderEndpointCatalogue(endpointCatalogue, listContainer, filterInput ? filterInput.value : '');
        if (filterInput) {
            filterInput.addEventListener('input', () => {
                renderEndpointCatalogue(endpointCatalogue, listContainer, filterInput.value);
            });
        }
    } catch (error) {
        console.error('Failed to load OpenAPI schema', error);
        listContainer.innerHTML = '';
        const paragraph = document.createElement('p');
        paragraph.textContent = 'Unable to load endpoint catalogue. Check that the API is running.';
        listContainer.appendChild(paragraph);
    }
}

function buildEndpointGroups(schema) {
    const groups = {};
    if (!schema || !schema.paths) {
        return groups;
    }
    Object.entries(schema.paths).forEach(([path, methods]) => {
        Object.entries(methods).forEach(([method, definition]) => {
            const tags = definition.tags && definition.tags.length ? definition.tags : ['untagged'];
            tags.forEach((tag) => {
                const key = tag.toLowerCase();
                if (!groups[key]) {
                    groups[key] = { label: tag, endpoints: [] };
                }
                groups[key].endpoints.push({
                    method: method.toUpperCase(),
                    path,
                    summary: definition.summary || definition.operationId || '',
                    tag
                });
            });
        });
    });
    return groups;
}

function renderEndpointCatalogue(groups, container, filterValue) {
    container.innerHTML = '';
    if (!groups || !Object.keys(groups).length) {
        const paragraph = document.createElement('p');
        paragraph.textContent = 'No endpoints found in the schema.';
        container.appendChild(paragraph);
        return;
    }

    const normalisedFilter = (filterValue || '').toLowerCase().trim();
    let matched = 0;

    Object.values(groups)
        .sort((a, b) => a.label.localeCompare(b.label))
        .forEach((group) => {
            const filtered = group.endpoints.filter((endpoint) => {
                if (!normalisedFilter) {
                    return true;
                }
                return (
                    group.label.toLowerCase().includes(normalisedFilter) ||
                    endpoint.path.toLowerCase().includes(normalisedFilter) ||
                    endpoint.summary.toLowerCase().includes(normalisedFilter)
                );
            });

            if (!filtered.length) {
                return;
            }
            matched += filtered.length;

            const groupEl = document.createElement('div');
            groupEl.className = 'endpoint-group';
            const heading = document.createElement('h4');
            heading.textContent = group.label;
            groupEl.appendChild(heading);

            filtered
                .sort((a, b) => a.path.localeCompare(b.path))
                .forEach((endpoint) => {
                    const item = document.createElement('div');
                    item.className = 'endpoint-item';
                    const method = document.createElement('span');
                    method.className = 'method';
                    method.textContent = endpoint.method;
                    const path = document.createElement('span');
                    path.className = 'path';
                    path.textContent = endpoint.path;
                    item.append(method, path);
                    if (endpoint.summary) {
                        const summary = document.createElement('span');
                        summary.className = 'muted';
                        summary.textContent = endpoint.summary;
                        item.appendChild(summary);
                    }
                    groupEl.appendChild(item);
                });

            container.appendChild(groupEl);
        });

    if (!matched) {
        const paragraph = document.createElement('p');
        paragraph.textContent = 'No endpoints match your filter.';
        container.appendChild(paragraph);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
