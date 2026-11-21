// Shared harness: loads script.js into a vm context with a minimal DOM stub.
// No browser, network or real files involved.

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function stubElement() {
  const el = {
    style: {},
    value: '',
    textContent: '',
    innerHTML: '',
    attrs: {},
    listeners: {},
    classes: new Set(),
    classList: {
      add: c => el.classes.add(c),
      remove: c => el.classes.delete(c),
      toggle: (c, on) => (on === undefined ? !el.classes.has(c) : on) ? el.classes.add(c) : el.classes.delete(c),
      contains: c => el.classes.has(c)
    },
    addEventListener: (type, fn) => { (el.listeners[type] = el.listeners[type] || []).push(fn); },
    setAttribute: (k, v) => { el.attrs[k] = v; },
    getAttribute: k => (k in el.attrs ? el.attrs[k] : null),
    removeAttribute: k => { delete el.attrs[k]; },
    getElementsByClassName: () => [],
    focus() {},
    closest: () => null
  };
  return el;
}

// `papa` lets a test fake CSV downloads: papa(path, options) -> calls options.complete / options.error.
function loadApp({ rows = null, papa = null, location = undefined } = {}) {
  const source = fs
    .readFileSync(process.env.SCRIPT_PATH || path.join(__dirname, '..', 'script.js'), 'utf8')
    .replace("document.addEventListener('DOMContentLoaded', setupLogin);", '');
  const els = {};
  const ctx = {
    console,
    Papa: { parse: (p, o) => (papa ? papa(p, o) : o.error(new Error('no Papa stub'))) },
    prompt() {},
    alert() {},
    document: {
      getElementById: id => els[id] || (els[id] = stubElement()),
      addEventListener() {}
    }
  };
  if (location) ctx.location = location;
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  if (rows) {
    ctx.__rows = rows;
    vm.runInContext('Object.assign(dataStore, __rows); buildCompanyIndex();', ctx);
  }
  return { ctx, els, run: code => vm.runInContext(code, ctx) };
}

let counter = 0;
function person(company, extra = {}) {
  counter += 1;
  return {
    'First Name': `P${counter}`,
    'Last Name': 'X',
    URL: `https://www.linkedin.com/in/p${counter}`,
    Company: company,
    Position: 'Engineer',
    ...extra
  };
}

// Arrays created inside the vm have a different Array.prototype, so assert.deepEqual
// would fail even when contents match. Round-trip to plain data first.
const plain = value => JSON.parse(JSON.stringify(value));

module.exports = { loadApp, person, plain, stubElement };
