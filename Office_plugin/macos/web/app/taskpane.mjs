// Task pane page and shared runtime: ribbon commands run here even while the
// pane is hidden (manifest Runtime lifetime="long").
/* global Office */
import {Controller} from './controller.mjs';
import {Pane} from './pane.mjs';

const pane = new Pane();

Office.onReady(async info => {
  const word = info.host === Office.HostType.Word;
  document.body.dataset.host = word ? 'word' : 'powerpoint';
  // The PowerPoint pane has no display/numbering options, like on Windows.
  if (!word) document.getElementById('optionsRow')?.remove();
  // Register the ribbon commands before loading the editor bundle: a command
  // that arrives while the runtime starts would otherwise be lost. Pane
  // updates sent meanwhile are queued until the pane is mounted.
  new Controller(info.host, pane).start();
  await pane.mount();
});
