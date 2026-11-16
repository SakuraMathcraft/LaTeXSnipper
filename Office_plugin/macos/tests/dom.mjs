// Gives the pure OOXML modules the DOM they get from the browser in Office.
import {DOMParser, XMLSerializer} from '@xmldom/xmldom';

globalThis.DOMParser = DOMParser;
globalThis.XMLSerializer = XMLSerializer;

const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
const M = 'http://schemas.openxmlformats.org/officeDocument/2006/math';

/** A flat-OPC package shaped like Office.js getOoxml() output. */
export function wordPackage(bodyXml, {styles = '', settings = ''} = {}) {
  const parts = [
    `<pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document xmlns:w="${W}" xmlns:m="${M}"><w:body>${bodyXml}</w:body></w:document></pkg:xmlData></pkg:part>`,
  ];
  if (styles) parts.push(`<pkg:part pkg:name="/word/styles.xml"><pkg:xmlData><w:styles xmlns:w="${W}">${styles}</w:styles></pkg:xmlData></pkg:part>`);
  if (settings) parts.push(`<pkg:part pkg:name="/word/settings.xml"><pkg:xmlData><w:settings xmlns:w="${W}">${settings}</w:settings></pkg:xmlData></pkg:part>`);
  return `<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">${parts.join('')}</pkg:package>`;
}

/** Body paragraphs of a package as [{text, xml}] for assertions. */
export function paragraphs(packageXml) {
  const document = new DOMParser().parseFromString(packageXml, 'application/xml');
  const body = document.getElementsByTagNameNS(W, 'body')[0];
  return [...body.childNodes].filter(node => node.localName === 'p').map(paragraph => ({
    text: [...paragraph.getElementsByTagNameNS(W, 't')].filter(t => !inside(t, 'sdt', paragraph))
      .map(t => t.textContent).join(''),
    tags: [...paragraph.getElementsByTagNameNS(W, 'tag')].map(tag => tag.getAttributeNS(W, 'val')),
    xml: new XMLSerializer().serializeToString(paragraph),
  }));
}

function inside(node, name, stop) {
  for (let current = node.parentNode; current && current !== stop; current = current.parentNode)
    if (current.localName === name) return true;
  return false;
}
