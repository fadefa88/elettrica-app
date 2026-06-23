import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'it.elettricaotermica.app',
  appName: 'Elettrica o Termica',
  webDir: 'www',
  server: {
    iosScheme: 'https'
  }
};

export default config;
