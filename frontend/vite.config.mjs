import { defineConfig } from 'vite'
import { transformAsync } from '@babel/core'
import presetReact from '@babel/preset-react'
import presetTypeScript from '@babel/preset-typescript'

const babelTsx = {
  name: 'babel-tsx-no-native-toolchain',
  enforce: 'pre',
  async transform(code, id) {
    if (!/\.[jt]sx?$/.test(id) || id.includes('/node_modules/')) return null
    const out = await transformAsync(code, {
      filename: id,
      sourceMaps: true,
      presets: [
        [presetTypeScript, { ignoreExtensions: false }],
        [presetReact, { runtime: 'automatic', development: process.env.NODE_ENV !== 'production' }],
      ],
    })
    return out ? { code: out.code, map: out.map } : null
  },
}

export default defineConfig({
  plugins: [babelTsx],
  esbuild: false,
  optimizeDeps: { noDiscovery: true, include: [] },
  build: { minify: 'terser', sourcemap: false, rollupOptions: { output: { manualChunks(id) {
    if (id.includes('/node_modules/three/') || id.includes('/node_modules/@react-three/')) return 'structural-3d'
    if (id.includes('/node_modules/recharts/') || id.includes('/node_modules/d3-')) return 'analytics-charts'
    if (id.includes('/node_modules/react/') || id.includes('/node_modules/scheduler/')) return 'react-core'
  } } } },
  server: { port: 5173, strictPort: true },
})
