import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';

export default defineConfig({
  site: 'https://jagadeshvarma.github.io',
  base: '/Structure-D',
  integrations: [
    mdx(),
  ],
  markdown: {
    shikiConfig: {
      theme: 'one-dark-pro',
      langs: ['python', 'typescript', 'javascript', 'bash', 'yaml', 'json', 'rust'],
      wrap: false,
    },
  },
});
