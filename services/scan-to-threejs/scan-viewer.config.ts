// Build only the original reconstruction viewer and comparison page. Upstream's
// optional playground imports a private office demo, excluded from its MIT license.
import { resolve } from 'node:path';
import upstream from './apps/room-viewer/vite.config.ts';

export default {
  ...upstream,
  plugins: [{
    name: 'reconstruction-only',
    transformIndexHtml(html: string) {
      // Keep the DOM node for upstream's event binding, but hide its unavailable
      // optional playground from this reconstruction-only build.
      return html.replace('<button class="play-link"', '<button hidden style="display:none" class="play-link"');
    },
  }],
  build: { ...upstream.build, rolldownOptions: { input: {
    main: resolve(import.meta.dirname, 'apps/room-viewer/index.html'),
    capture: resolve(import.meta.dirname, 'apps/room-viewer/tools/capture.html'),
  } } },
};
