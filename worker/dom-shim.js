// 同花顺 hexin-v 反爬脚本所需的浏览器环境垫片。
// 原脚本依赖 jsdom（打包后 5.1MB），实测其真实 DOM 依赖极少，
// 用本垫片即可在纯 V8 环境（Cloudflare Worker）中直接运行。
export const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

function makeStore() {
  const s = Object.create(null);
  return {
    getItem: (k) => (k in s ? s[k] : null),
    setItem: (k, v) => {
      s[k] = String(v);
    },
    removeItem: (k) => {
      delete s[k];
    },
    clear: () => {
      for (const k in s) delete s[k];
    },
    key: (i) => Object.keys(s)[i] ?? null,
    get length() {
      return Object.keys(s).length;
    },
  };
}

function makeEl(tag) {
  const name = String(tag || 'div');
  return {
    tagName: name.toUpperCase(),
    nodeName: name.toUpperCase(),
    nodeType: 1,
    style: {},
    children: [],
    childNodes: [],
    attributes: {},
    src: '',
    id: '',
    className: '',
    innerHTML: '',
    innerText: '',
    textContent: '',
    parentNode: null,
    offsetWidth: 0,
    offsetHeight: 0,
    clientWidth: 0,
    clientHeight: 0,
    setAttribute(k, v) {
      this.attributes[k] = String(v);
    },
    getAttribute(k) {
      return k in this.attributes ? this.attributes[k] : null;
    },
    removeAttribute(k) {
      delete this.attributes[k];
    },
    hasAttribute(k) {
      return k in this.attributes;
    },
    appendChild(c) {
      this.children.push(c);
      this.childNodes.push(c);
      if (c) c.parentNode = this;
      return c;
    },
    insertBefore(c) {
      return this.appendChild(c);
    },
    removeChild(c) {
      return c;
    },
    remove() {},
    addEventListener() {},
    removeEventListener() {},
    attachEvent() {},
    detachEvent() {},
    getContext() {
      return null;
    },
    getElementsByTagName() {
      return [];
    },
    getElementById() {
      return null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    focus() {},
    blur() {},
    click() {},
    cloneNode() {
      return makeEl(name);
    },
  };
}

function b64encode(str) {
  const bytes = new TextEncoder().encode(String(str));
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64decode(str) {
  const bin = atob(String(str));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

export function createShims() {
  const localStorage = makeStore();
  const sessionStorage = makeStore();

  const navigator = {
    userAgent: UA,
    appName: 'Netscape',
    appCodeName: 'Mozilla',
    appVersion: UA.replace('Mozilla/', ''),
    platform: 'Win32',
    vendor: 'Google Inc.',
    vendorSub: '',
    product: 'Gecko',
    productSub: '20030107',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh'],
    systemLanguage: 'zh-CN',
    userLanguage: 'zh-CN',
    cookieEnabled: true,
    onLine: true,
    webdriver: false,
    doNotTrack: null,
    hardwareConcurrency: 8,
    maxTouchPoints: 0,
    deviceMemory: 8,
    plugins: Object.assign([], { length: 0 }),
    mimeTypes: Object.assign([], { length: 0 }),
    javaEnabled() {
      return false;
    },
    sendBeacon() {
      return true;
    },
    registerProtocolHandler() {},
  };

  const location = {
    href: 'http://q.10jqka.com.cn/',
    protocol: 'http:',
    host: 'q.10jqka.com.cn',
    hostname: 'q.10jqka.com.cn',
    port: '',
    pathname: '/',
    search: '',
    hash: '',
    origin: 'http://q.10jqka.com.cn',
    replace() {},
    assign() {},
    reload() {},
  };

  const screen = {
    width: 1920,
    height: 1080,
    availWidth: 1920,
    availHeight: 1040,
    colorDepth: 24,
    pixelDepth: 24,
    deviceXDPI: 96,
    deviceYDPI: 96,
    logicalXDPI: 96,
    logicalYDPI: 96,
  };

  const document = {
    cookie: '',
    title: 'q.10jqka.com.cn',
    referrer: '',
    URL: 'http://q.10jqka.com.cn/',
    domain: '10jqka.com.cn',
    characterSet: 'UTF-8',
    charset: 'UTF-8',
    inputEncoding: 'UTF-8',
    readyState: 'complete',
    visibilityState: 'visible',
    hidden: false,
    compatMode: 'CSS1Compat',
    documentMode: undefined,
    createElement: makeEl,
    createElementNS: (ns, t) => makeEl(t),
    createTextNode: () => makeEl('#text'),
    createComment: () => makeEl('#comment'),
    createDocumentFragment: () => makeEl('#fragment'),
    getElementById: () => null,
    getElementsByTagName: () => [],
    getElementsByClassName: () => [],
    getElementsByName: () => [],
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    removeEventListener() {},
    attachEvent() {},
    detachEvent() {},
    write() {},
    writeln() {},
    hasFocus() {
      return true;
    },
  };
  document.head = makeEl('head');
  document.body = makeEl('body');
  document.documentElement = makeEl('html');
  document.documentElement.appendChild(document.head);
  document.documentElement.appendChild(document.body);
  document.location = location;

  const XMLHttpRequest = function XMLHttpRequestShim() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
    this.open = () => {};
    this.send = () => {};
    this.setRequestHeader = () => {};
    this.getAllResponseHeaders = () => '';
    this.addEventListener = () => {};
    this.abort = () => {};
  };

  const window = {
    document,
    navigator,
    location,
    screen,
    localStorage,
    sessionStorage,
    name: '',
    closed: false,
    length: 0,
    innerWidth: 1920,
    innerHeight: 947,
    outerWidth: 1920,
    outerHeight: 1080,
    screenLeft: 0,
    screenTop: 0,
    screenX: 0,
    screenY: 0,
    scrollX: 0,
    scrollY: 0,
    pageXOffset: 0,
    pageYOffset: 0,
    devicePixelRatio: 1,
    opener: null,
    addEventListener() {},
    removeEventListener() {},
    attachEvent() {},
    detachEvent() {},
    setTimeout,
    setInterval,
    clearTimeout,
    clearInterval,
    requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 16),
    cancelAnimationFrame: clearTimeout,
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    matchMedia: () => ({
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }),
    postMessage() {},
    open: () => null,
    close() {},
    focus() {},
    blur() {},
    scrollTo() {},
    scrollBy() {},
    alert() {},
    confirm: () => true,
    prompt: () => null,
    btoa: b64encode,
    atob: b64decode,
    escape: (s) => encodeURIComponent(s),
    unescape: (s) => decodeURIComponent(s),
    performance: { now: () => Date.now(), timing: {}, navigation: {} },
    console,
    XMLHttpRequest,
    Image: function Image() {
      return makeEl('img');
    },
  };
  window.window = window;
  window.self = window;
  window.top = window;
  window.parent = window;
  window.frames = window;

  return {
    window,
    document,
    navigator,
    location,
    screen,
    localStorage,
    sessionStorage,
    top: window,
    parent: window,
    frames: window,
    self: window,
    ActiveXObject: undefined,
    XMLHttpRequest,
    Image: function Image() {
      return makeEl('img');
    },
    escape: (s) => encodeURIComponent(s),
    unescape: (s) => decodeURIComponent(s),
    btoa: b64encode,
    atob: b64decode,
    setImmediate: (fn) => setTimeout(fn, 0),
    process: { env: {}, version: 'v22.0.0', platform: 'linux', nextTick: (f) => setTimeout(f, 0) },
    Buffer: undefined,
    postMessage: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
  };
}
