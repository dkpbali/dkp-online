import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  base: './', // Relative base path for portable builds (works on local file:// and subfolders on GitHub Pages)
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        aset: resolve(__dirname, 'aset/index.html'),
        aset_qr: resolve(__dirname, 'aset/qr.html'),
        bbm: resolve(__dirname, 'bbm/index.html'),
        helpdesk: resolve(__dirname, 'helpdesk/index.html'),
        rapat: resolve(__dirname, 'rapat/index.html'),
        humas: resolve(__dirname, 'humas/index.html'),
        kendaraan: resolve(__dirname, 'kendaraan/index.html'),
        dashboard_kendaraan: resolve(__dirname, 'dashboard/dashboard_kendaraan/index.html'),
        dashboard_ekspor: resolve(__dirname, 'dashboard/dashboard_ekspor/index.html'),
        dashboard_ews: resolve(__dirname, 'dashboard/dashboard_ews/index.html'),
        dashboard_ews_verifikasi: resolve(__dirname, 'dashboard/dashboard_ews/verifikasi.html')
      }
    }
  }
});
