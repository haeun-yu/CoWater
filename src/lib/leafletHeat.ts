import L from 'leaflet';

type HeatDatum = [number, number, number];

type SimpleHeatInstance = {
  _width: number;
  _height: number;
  _r: number;
  defaultRadius: number;
  defaultGradient: Record<number, string>;
  data(data: HeatDatum[]): SimpleHeatInstance;
  max(value: number): SimpleHeatInstance;
  clear(): SimpleHeatInstance;
  radius(radius: number, blur?: number): SimpleHeatInstance;
  gradient(gradient: Record<number, string>): SimpleHeatInstance;
  draw(minOpacity?: number): SimpleHeatInstance;
};

const get2dContext = (canvas: HTMLCanvasElement) =>
  canvas.getContext('2d', { willReadFrequently: true }) ?? canvas.getContext('2d');

function simpleheat(canvas: HTMLCanvasElement): SimpleHeatInstance {
  const context = get2dContext(canvas);
  if (!context) {
    throw new Error('2D canvas context is unavailable');
  }

  const heat = {
    _canvas: canvas,
    _ctx: context,
    _width: canvas.width,
    _height: canvas.height,
    _max: 1,
    _data: [] as HeatDatum[],
    _circle: null as HTMLCanvasElement | null,
    _grad: null as Uint8ClampedArray | null,
    _r: 0,

    defaultRadius: 25,
    defaultGradient: { 0.4: 'blue', 0.6: 'cyan', 0.7: 'lime', 0.8: 'yellow', 1: 'red' },

    data(data: HeatDatum[]) {
      this._data = data;
      return this;
    },

    max(value: number) {
      this._max = value;
      return this;
    },

    clear() {
      this._data = [];
      return this;
    },

    radius(radius: number, blur = 15) {
      const circle = (this._circle = document.createElement('canvas'));
      const circleContext = get2dContext(circle);
      if (!circleContext) {
        throw new Error('2D canvas context is unavailable');
      }

      const extent = (this._r = radius + blur);
      circle.width = circle.height = extent * 2;
      circleContext.shadowOffsetX = circleContext.shadowOffsetY = 200;
      circleContext.shadowBlur = blur;
      circleContext.shadowColor = 'black';
      circleContext.beginPath();
      circleContext.arc(extent - 200, extent - 200, radius, 0, Math.PI * 2, true);
      circleContext.closePath();
      circleContext.fill();
      return this;
    },

    gradient(gradient: Record<number, string>) {
      const palette = document.createElement('canvas');
      const paletteContext = get2dContext(palette);
      if (!paletteContext) {
        throw new Error('2D canvas context is unavailable');
      }

      palette.width = 1;
      palette.height = 256;

      const linearGradient = paletteContext.createLinearGradient(0, 0, 0, 256);
      for (const stop in gradient) {
        linearGradient.addColorStop(Number(stop), gradient[Number(stop)]);
      }

      paletteContext.fillStyle = linearGradient;
      paletteContext.fillRect(0, 0, 1, 256);
      this._grad = paletteContext.getImageData(0, 0, 1, 256).data;
      return this;
    },

    draw(minOpacity = 0.05) {
      if (!this._circle) {
        this.radius(this.defaultRadius);
      }
      if (!this._grad) {
        this.gradient(this.defaultGradient);
      }

      this._ctx.clearRect(0, 0, this._width, this._height);

      for (let index = 0; index < this._data.length; index += 1) {
        const point = this._data[index];
        this._ctx.globalAlpha = Math.max(point[2] / this._max, minOpacity);
        this._ctx.drawImage(this._circle!, point[0] - this._r, point[1] - this._r);
      }

      const colored = this._ctx.getImageData(0, 0, this._width, this._height);
      for (let index = 3; index < colored.data.length; index += 4) {
        const alpha = colored.data[index] * 4;
        if (!alpha) {
          continue;
        }

        colored.data[index - 3] = this._grad![alpha];
        colored.data[index - 2] = this._grad![alpha + 1];
        colored.data[index - 1] = this._grad![alpha + 2];
      }

      this._ctx.putImageData(colored, 0, 0);
      return this;
    },
  };

  return heat.clear();
}

type HeatOptions = {
  minOpacity?: number;
  maxZoom?: number;
  radius?: number;
  blur?: number;
  max?: number;
  gradient?: Record<number, string>;
};

const HeatLayer = (L.Layer ? L.Layer : L.Class).extend({
  initialize(this: any, latlngs: HeatDatum[], options?: HeatOptions) {
    this._latlngs = latlngs;
    L.setOptions(this, options);
  },

  setLatLngs(this: any, latlngs: HeatDatum[]) {
    this._latlngs = latlngs;
    return this.redraw();
  },

  redraw(this: any) {
    if (this._heat && !this._frame && !this._map._animating) {
      this._frame = L.Util.requestAnimFrame(this._redraw, this);
    }
    return this;
  },

  onAdd(this: any, map: L.Map) {
    this._map = map;

    if (!this._canvas) {
      this._initCanvas();
    }

    map.getPanes().overlayPane.appendChild(this._canvas);
    map.on('moveend', this._reset, this);

    if (map.options.zoomAnimation && L.Browser.any3d) {
      map.on('zoomanim', this._animateZoom, this);
    }

    this._reset();
  },

  onRemove(this: any, map: L.Map) {
    map.getPanes().overlayPane.removeChild(this._canvas);
    map.off('moveend', this._reset, this);

    if (map.options.zoomAnimation) {
      map.off('zoomanim', this._animateZoom, this);
    }
  },

  _initCanvas(this: any) {
    const canvas = (this._canvas = L.DomUtil.create('canvas', 'leaflet-heatmap-layer leaflet-layer'));
    const originProp = L.DomUtil.testProp(['transformOrigin', 'WebkitTransformOrigin', 'msTransformOrigin']) as string;
    (canvas.style as CSSStyleDeclaration & Record<string, string>)[originProp] = '50% 50%';

    const size = this._map.getSize();
    canvas.width = size.x;
    canvas.height = size.y;

    const animated = this._map.options.zoomAnimation && L.Browser.any3d;
    L.DomUtil.addClass(canvas, `leaflet-zoom-${animated ? 'animated' : 'hide'}`);

    this._heat = simpleheat(canvas);
    this._updateOptions();
  },

  _updateOptions(this: any) {
    this._heat.radius(this.options.radius || this._heat.defaultRadius, this.options.blur);
    if (this.options.gradient) {
      this._heat.gradient(this.options.gradient);
    }
    if (this.options.max) {
      this._heat.max(this.options.max);
    }
  },

  _reset(this: any) {
    const topLeft = this._map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(this._canvas, topLeft);

    const size = this._map.getSize();
    if (this._heat._width !== size.x) {
      this._canvas.width = this._heat._width = size.x;
    }
    if (this._heat._height !== size.y) {
      this._canvas.height = this._heat._height = size.y;
    }

    this._redraw();
  },

  _redraw(this: any) {
    const data: HeatDatum[] = [];
    const radius = this._heat._r;
    const size = this._map.getSize();
    const bounds = new L.Bounds(L.point([-radius, -radius]), size.add([radius, radius]));
    const max = this.options.max === undefined ? 1 : this.options.max;
    const maxZoom = this.options.maxZoom === undefined ? this._map.getMaxZoom() : this.options.maxZoom;
    const zoomFactor = 1 / Math.pow(2, Math.max(0, Math.min(maxZoom - this._map.getZoom(), 12)));
    const cellSize = radius / 2;
    const grid: Array<Array<[number, number, number] | undefined> | undefined> = [];
    const panePos = this._map._getMapPanePos();
    const offsetX = panePos.x % cellSize;
    const offsetY = panePos.y % cellSize;

    for (let index = 0; index < this._latlngs.length; index += 1) {
      const point = this._map.latLngToContainerPoint(this._latlngs[index]);
      if (!bounds.contains(point)) {
        continue;
      }

      const x = Math.floor((point.x - offsetX) / cellSize) + 2;
      const y = Math.floor((point.y - offsetY) / cellSize) + 2;
      const alt =
        this._latlngs[index].alt !== undefined
          ? this._latlngs[index].alt
          : this._latlngs[index][2] !== undefined
            ? +this._latlngs[index][2]
            : 1;
      const value = alt * zoomFactor;

      grid[y] = grid[y] || [];
      const cell = grid[y]![x];

      if (!cell) {
        grid[y]![x] = [point.x, point.y, value];
        continue;
      }

      cell[0] = (cell[0] * cell[2] + point.x * value) / (cell[2] + value);
      cell[1] = (cell[1] * cell[2] + point.y * value) / (cell[2] + value);
      cell[2] += value;
    }

    for (let y = 0; y < grid.length; y += 1) {
      if (!grid[y]) {
        continue;
      }

      for (let x = 0; x < grid[y]!.length; x += 1) {
        const cell = grid[y]![x];
        if (!cell) {
          continue;
        }

        data.push([Math.round(cell[0]), Math.round(cell[1]), Math.min(cell[2], max)]);
      }
    }

    this._heat.data(data).draw(this.options.minOpacity);
    this._frame = null;
  },

  _animateZoom(this: any, event: L.ZoomAnimEvent) {
    const scale = this._map.getZoomScale(event.zoom);
    const offset = this._map._getCenterOffset(event.center)._multiplyBy(-scale).subtract(this._map._getMapPanePos());

    if (L.DomUtil.setTransform) {
      L.DomUtil.setTransform(this._canvas, offset, scale);
      return;
    }

    this._canvas.style[(L.DomUtil as typeof L.DomUtil & { TRANSFORM: string }).TRANSFORM] =
      `${(L.DomUtil as typeof L.DomUtil & { getTranslateString(point: L.Point): string }).getTranslateString(offset)} scale(${scale})`;
  },
});

(L as typeof L & { HeatLayer: typeof HeatLayer; heatLayer: (latlngs: HeatDatum[], options?: HeatOptions) => L.Layer }).HeatLayer =
  HeatLayer;
(L as typeof L & { heatLayer: (latlngs: HeatDatum[], options?: HeatOptions) => L.Layer }).heatLayer = (
  latlngs: HeatDatum[],
  options?: HeatOptions,
) => new (HeatLayer as new (points: HeatDatum[], opts?: HeatOptions) => L.Layer)(latlngs, options);

export {};
