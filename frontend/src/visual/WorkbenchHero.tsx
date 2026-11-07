import { useEffect, useRef, useState } from 'react'

type HeroMode = 'shader' | 'static' | 'image'
type HeroVariant = 'fluid' | 'lab' | 'molecule' | 'data'

const VERTEX = `
attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`

const FRAGMENT = `
precision mediump float;
uniform vec2 u_resolution;
uniform float u_time;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.02 + vec2(1.7, 9.2);
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  float aspect = u_resolution.x / max(u_resolution.y, 1.0);
  vec2 p = (uv - 0.5) * vec2(aspect, 1.0);
  float t = u_time * 0.08;

  float field = fbm(p * 2.4 + vec2(t * 0.6, -t * 0.35));
  float ripples = sin((field * 6.2831) + t * 2.4) * 0.5 + 0.5;
  float bands = smoothstep(0.25, 0.85, fbm(p * 1.4 - vec2(t * 0.2, t * 0.15)));

  vec3 paper = vec3(0.973, 0.980, 0.988);
  vec3 mist = vec3(0.890, 0.925, 0.973);
  vec3 ink = vec3(0.145, 0.388, 0.922);
  vec3 deep = vec3(0.114, 0.306, 0.847);
  vec3 teal = vec3(0.086, 0.525, 0.561);

  vec3 color = mix(paper, mist, bands);
  color = mix(color, ink * 0.22 + paper * 0.78, ripples * 0.55);
  color = mix(color, teal * 0.18 + paper * 0.82, smoothstep(0.4, 0.9, field) * 0.45);
  color += deep * 0.04 * (1.0 - uv.y);

  float vignette = smoothstep(1.15, 0.25, length((uv - 0.5) * vec2(1.15, 1.0)));
  color *= 0.94 + 0.06 * vignette;
  gl_FragColor = vec4(color, 1.0);
}
`

function prefersReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function createShader(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)
  if (!shader) return null
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    return null
  }
  return shader
}

function createProgram(gl: WebGLRenderingContext) {
  const vertex = createShader(gl, gl.VERTEX_SHADER, VERTEX)
  const fragment = createShader(gl, gl.FRAGMENT_SHADER, FRAGMENT)
  if (!vertex || !fragment) return null
  const program = gl.createProgram()
  if (!program) return null
  gl.attachShader(program, vertex)
  gl.attachShader(program, fragment)
  gl.linkProgram(program)
  gl.deleteShader(vertex)
  gl.deleteShader(fragment)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program)
    return null
  }
  return program
}

const IMAGE_VARIANTS: Record<Exclude<HeroVariant, 'fluid'>, string> = {
  lab: '/media/hero/hero-lab.jpg',
  molecule: '/media/hero/hero-molecule.jpg',
  data: '/media/hero/hero-data.jpg',
}

/**
 * Workbench atmosphere hero: native WebGL fluid by default, with static CSS /
 * image fallbacks for reduced-motion, hidden tabs, and WebGL failures.
 */
export function WorkbenchHero({ variant = 'fluid', reduceMotion = false }: { variant?: HeroVariant; reduceMotion?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [mode, setMode] = useState<HeroMode>(() => {
    if (variant !== 'fluid') return 'image'
    if (reduceMotion || prefersReducedMotion()) return 'static'
    return 'shader'
  })

  useEffect(() => {
    if (variant !== 'fluid') {
      setMode('image')
      return
    }
    if (reduceMotion || prefersReducedMotion()) {
      setMode('static')
      return
    }
    setMode('shader')
  }, [variant, reduceMotion])

  useEffect(() => {
    if (mode !== 'shader') return
    const canvas = canvasRef.current
    if (!canvas) return

    const gl = canvas.getContext('webgl', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
    })
    if (!gl) {
      setMode('static')
      return
    }

    const program = createProgram(gl)
    if (!program) {
      setMode('static')
      return
    }

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1, -1, 1, -1, -1, 1,
      -1, 1, 1, -1, 1, 1,
    ]), gl.STATIC_DRAW)

    const position = gl.getAttribLocation(program, 'a_position')
    const resolution = gl.getUniformLocation(program, 'u_resolution')
    const time = gl.getUniformLocation(program, 'u_time')
    gl.useProgram(program)
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)

    let frame = 0
    let running = true
    let start = performance.now()
    const maxDpr = 1.25

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, maxDpr)
      const width = Math.max(1, Math.floor(rect.width * dpr))
      const height = Math.max(1, Math.floor(rect.height * dpr))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
        gl.viewport(0, 0, width, height)
      }
    }

    const draw = (now: number) => {
      if (!running) return
      resize()
      gl.uniform2f(resolution, canvas.width, canvas.height)
      gl.uniform1f(time, (now - start) / 1000)
      gl.drawArrays(gl.TRIANGLES, 0, 6)
      frame = window.requestAnimationFrame(draw)
    }

    const onVisibility = () => {
      if (document.hidden) {
        running = false
        window.cancelAnimationFrame(frame)
      } else if (!prefersReducedMotion()) {
        running = true
        start = performance.now() - ((performance.now() - start) % 60000)
        frame = window.requestAnimationFrame(draw)
      } else {
        setMode('static')
      }
    }

    const onMotion = (event: MediaQueryListEvent) => {
      if (event.matches) setMode('static')
    }

    const motionQuery = typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null
    motionQuery?.addEventListener?.('change', onMotion)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('resize', resize)
    resize()
    frame = window.requestAnimationFrame(draw)

    return () => {
      running = false
      window.cancelAnimationFrame(frame)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('resize', resize)
      motionQuery?.removeEventListener?.('change', onMotion)
      gl.deleteBuffer(buffer)
      gl.deleteProgram(program)
    }
  }, [mode])

  const imageSrc = variant === 'fluid' ? undefined : IMAGE_VARIANTS[variant]

  return (
    <div
      className={'workbench-hero' + (mode === 'static' ? ' workbench-hero--static' : '') + (mode === 'image' ? ' workbench-hero--image' : '')}
      data-hero-mode={mode}
      data-hero-variant={variant}
      aria-hidden="true"
    >
      {mode === 'shader' && <canvas ref={canvasRef} className="workbench-hero__canvas" />}
      {mode === 'image' && imageSrc && (
        <img
          className="workbench-hero__image"
          src={imageSrc}
          alt=""
          onError={() => setMode('static')}
        />
      )}
      <div className="workbench-hero__veil" />
      <div className="workbench-hero__noise" />
    </div>
  )
}
