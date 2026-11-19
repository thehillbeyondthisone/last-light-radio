// Shared integer geometry with last_light_radio/texture.py.
export const TEXTURE_TILE = 256
export function mix(value: number) {
  value = Math.imul(value ^ (value >>> 16), 0x7feb352d)
  value = Math.imul(value ^ (value >>> 15), 0x846ca68b)
  return (value ^ (value >>> 16)) >>> 0
}
export function textureOffset(seed: number, frame: number) {
  const value = seed ^ Math.imul(frame + 1, 0x9e3779b9)
  return [mix(value) % TEXTURE_TILE, mix(value ^ 0xa5a5a5a5) % TEXTURE_TILE]
}
export function textureTile(seed: number) {
  let state = (seed ^ 0x9e3779b9) >>> 0
  const pixels = new Uint8ClampedArray(TEXTURE_TILE * TEXTURE_TILE * 4)
  for (let index = 0; index < pixels.length; index += 4) {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5
    const value = Math.floor(((state & 255) + ((state >>> 8) & 255) + ((state >>> 16) & 255)) / 3)
    pixels[index] = pixels[index + 1] = pixels[index + 2] = value
    pixels[index + 3] = 255
  }
  return pixels
}
