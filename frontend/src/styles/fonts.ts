// Field Ledger typefaces (ADR-069), bundled with the app so it works offline and under the build's
// Content-Security-Policy (font-src 'self'). All four are SIL Open Font Licence.
//
//  - Hind: body text, Latin and Devanagari.
//  - Zilla Slab: headings (Latin only).
//  - Martel: headings in Hindi. Only its Devanagari subset is loaded; the browser takes Hindi letters from it
//    because Zilla Slab has none (font-family: 'Zilla Slab', 'Martel', ...).
//  - JetBrains Mono: keys and codes (GG-001, T-004), figures in tables.
import '@fontsource/hind/latin-400.css'
import '@fontsource/hind/latin-500.css'
import '@fontsource/hind/latin-600.css'
import '@fontsource/hind/devanagari-400.css'
import '@fontsource/hind/devanagari-500.css'
import '@fontsource/hind/devanagari-600.css'
import '@fontsource/zilla-slab/latin-600.css'
import '@fontsource/zilla-slab/latin-700.css'
import '@fontsource/martel/devanagari-700.css'
import '@fontsource/jetbrains-mono/latin-400.css'
import '@fontsource/jetbrains-mono/latin-500.css'
