import React, { useState } from 'react'

const NUMERIC_FIELDS = [
  { key: 'air_temperature', label: '공기온도' },
  { key: 'process_temperature', label: '공정온도' },
  { key: 'rotational_speed', label: '회전속도' },
  { key: 'torque', label: '토크' },
  { key: 'tool_wear', label: '공구마모' },
]

// Build an input_features object from the form values, including only filled
// fields. Returns null when every field is empty (so the caller can omit it).
export function buildInputFeatures(values) {
  const out = {}
  if (values.type) out.type = values.type
  for (const { key } of NUMERIC_FIELDS) {
    const raw = values[key]
    if (raw !== '' && raw !== undefined && raw !== null) {
      const num = Number(raw)
      if (!Number.isNaN(num)) out[key] = num
    }
  }
  return Object.keys(out).length > 0 ? out : null
}

export const EMPTY_FEATURES = {
  type: '',
  air_temperature: '',
  process_temperature: '',
  rotational_speed: '',
  torque: '',
  tool_wear: '',
}

export default function FeatureInputs({ values, onChange, disabled }) {
  const [open, setOpen] = useState(false)

  const set = (key, val) => onChange({ ...values, [key]: val })

  return (
    <div className="feature-inputs">
      <button
        type="button"
        className="collapse-toggle"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? '▼' : '▶'} 데이터 입력란 (선택)
      </button>
      {open && (
        <div className="feature-grid">
          <label className="field">
            <span>제품 타입</span>
            <select
              value={values.type}
              onChange={(e) => set('type', e.target.value)}
              disabled={disabled}
            >
              <option value="">선택 안 함</option>
              <option value="L">L</option>
              <option value="M">M</option>
              <option value="H">H</option>
            </select>
          </label>
          {NUMERIC_FIELDS.map(({ key, label }) => (
            <label className="field" key={key}>
              <span>{label}</span>
              <input
                type="number"
                step="any"
                value={values[key]}
                onChange={(e) => set(key, e.target.value)}
                disabled={disabled}
                placeholder="(선택)"
              />
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
