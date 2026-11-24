"""Client-side JavaScript evasions and fingerprint spoofing for Android Pixel 7 emulation."""

from __future__ import annotations

# JavaScript injected into every page via add_init_script before any page script executes.
STEALTH_SCRIPT = """
(() => {
    'use strict';

    // 1. Delete navigator.webdriver and prevent detection via getOwnPropertyDescriptor
    try {
        const newProto = Object.getPrototypeOf(navigator);
        delete newProto.webdriver;
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true,
            enumerable: true
        });
    } catch (e) {}

    // 2. Hardware and device specifications (Pixel 7 / Android 14)
    try {
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
        Object.defineProperty(navigator, 'platform', { get: () => 'Linux armv8l' });
    } catch (e) {}

    // 3. User-Agent Data (Client Hints) for Chrome 131 on Android
    try {
        if (navigator.userAgentData) {
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => ({
                    brands: [
                        { brand: 'Google Chrome', version: '131' },
                        { brand: 'Chromium', version: '131' },
                        { brand: 'Not_A Brand', version: '24' }
                    ],
                    mobile: true,
                    platform: 'Android',
                    getHighEntropyValues: async (hints) => ({
                        architecture: 'arm',
                        bitness: '64',
                        brands: [
                            { brand: 'Google Chrome', version: '131' },
                            { brand: 'Chromium', version: '131' },
                            { brand: 'Not_A Brand', version: '24' }
                        ],
                        mobile: true,
                        model: 'Pixel 7',
                        platform: 'Android',
                        platformVersion: '14.0.0',
                        uaFullVersion: '131.0.6778.39'
                    })
                })
            });
        }
    } catch (e) {}

    // 4. WebGL / WebGL2 spoofing (Adreno 740 / Qualcomm)
    try {
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {
            // UNMASKED_VENDOR_WEBGL
            if (param === 0x9245) return 'Qualcomm';
            // UNMASKED_RENDERER_WEBGL
            if (param === 0x9246) return 'Adreno (TM) 740';
            return getParameterProto.apply(this, arguments);
        };

        if (window.WebGL2RenderingContext) {
            const getParameter2Proto = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {
                if (param === 0x9245) return 'Qualcomm';
                if (param === 0x9246) return 'Adreno (TM) 740';
                return getParameter2Proto.apply(this, arguments);
            };
        }
    } catch (e) {}

    // 5. Canvas Fingerprint subtle consistent noise
    try {
        const toBlobProto = HTMLCanvasElement.prototype.toBlob;
        const toDataURLProto = HTMLCanvasElement.prototype.toDataURL;
        const getImageDataProto = CanvasRenderingContext2D.prototype.getImageData;

        // Deterministic subtle noise based on canvas dimension
        function addNoise(canvas, context) {
            const width = canvas.width;
            const height = canvas.height;
            if (width > 0 && height > 0) {
                try {
                    const imageData = getImageDataProto.call(context, 0, 0, width, height);
                    for (let i = 0; i < imageData.data.length; i += 128) {
                        imageData.data[i] = (imageData.data[i] + 1) % 256;
                    }
                    context.putImageData(imageData, 0, 0);
                } catch (e) {}
            }
        }

        HTMLCanvasElement.prototype.toDataURL = function() {
            const ctx = this.getContext('2d');
            if (ctx) addNoise(this, ctx);
            return toDataURLProto.apply(this, arguments);
        };
    } catch (e) {}

    // 6. AudioContext subtle noise
    try {
        if (window.AudioBuffer) {
            const copyFromChannelProto = AudioBuffer.prototype.copyFromChannel;
            AudioBuffer.prototype.copyFromChannel = function(destination, channelNumber, startInChannel) {
                copyFromChannelProto.apply(this, arguments);
                for (let i = 0; i < destination.length; i += 100) {
                    destination[i] += 0.0000001;
                }
            };
        }
    } catch (e) {}

    // 7. Chrome runtime mock
    try {
        if (!window.chrome) {
            window.chrome = {
                app: { isInstalled: false },
                runtime: {
                    PlatformOs: { ANDROID: 'android' },
                    PlatformArch: { ARM: 'arm' }
                }
            };
        }
    } catch (e) {}

    // 8. Notification permission query
    try {
        const origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                origQuery(parameters)
        );
    } catch (e) {}
})();
"""
