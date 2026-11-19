// Run: node frontend/checks/menus.check.ts
// Every menu command must exist in the registry and be handled by the Film editor (a `case '<id>'` in FilmEditor.tsx).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { COMMAND_BY_ID } from '../src/shortcuts.ts'
import { MENU_COMMANDS } from '../src/filmMenus.ts'

const editor = readFileSync(new URL('../src/FilmEditor.tsx', import.meta.url), 'utf8')
const missing = MENU_COMMANDS.filter(id => !COMMAND_BY_ID.has(id))
const unhandled = MENU_COMMANDS.filter(id => !editor.includes(`case '${id}'`))
assert.deepEqual(missing, [], `menu ids not in the registry: ${missing}`)
assert.deepEqual(unhandled, [], `menu ids the Film editor does not handle: ${unhandled}`)
assert.equal(new Set(MENU_COMMANDS).size, MENU_COMMANDS.length, 'a command appears in two menus')
console.log(`${MENU_COMMANDS.length} menu commands checked`)
