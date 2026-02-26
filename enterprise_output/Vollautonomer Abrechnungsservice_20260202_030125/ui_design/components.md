# Component Library

## Button

**ID:** `COMP-001`
**Type:** button

Primary action button component

### Variants

- `primary`
- `secondary`
- `outline`
- `ghost`
- `danger`

### Props

| Prop | Type |
|------|------|
| `size` | `sm | md | lg` |
| `disabled` | `boolean` |
| `loading` | `boolean` |
| `icon` | `ReactNode (optional)` |
| `onClick` | `() => void` |

### States

- default
- hover
- active
- focus
- disabled
- loading

### Accessibility

- **role:** button
- **aria-label:** Required for icon-only buttons
- **aria-disabled:** When disabled

### Example

```tsx
<Button variant='primary' size='md'>Save</Button>
```

---

## InputField

**ID:** `COMP-002`
**Type:** input

Text input with label, hint and validation

### Variants

- `default`
- `filled`
- `outline`

### Props

| Prop | Type |
|------|------|
| `label` | `string` |
| `placeholder` | `string` |
| `value` | `string` |
| `onChange` | `(value: string) => void` |
| `type` | `text | email | number | password` |
| `required` | `boolean` |
| `error` | `string (optional)` |
| `helperText` | `string (optional)` |
| `icon` | `ReactNode (optional)` |

### States

- default
- focus
- error
- disabled

### Accessibility

- **role:** textbox
- **aria-label:** Input label
- **aria-invalid:** When error

### Example

```tsx
<InputField label='IBAN' placeholder='DE..' required />
```

---

## Select

**ID:** `COMP-003`
**Type:** select

Dropdown select for single or multi selection

### Variants

- `default`
- `searchable`
- `multi`

### Props

| Prop | Type |
|------|------|
| `label` | `string` |
| `options` | `Array<{label: string, value: string}>` |
| `value` | `string | string[]` |
| `onChange` | `(value: string | string[]) => void` |
| `placeholder` | `string` |
| `disabled` | `boolean` |
| `error` | `string (optional)` |

### States

- default
- focus
- open
- error
- disabled

### Accessibility

- **role:** combobox
- **aria-expanded:** When open
- **aria-label:** Select label

### Example

```tsx
<Select label='Currency' options={opts} />
```

---

## DataTable

**ID:** `COMP-004`
**Type:** table

Sortable, filterable data table

### Variants

- `default`
- `compact`
- `striped`

### Props

| Prop | Type |
|------|------|
| `columns` | `Column[]` |
| `data` | `T[]` |
| `sortable` | `boolean` |
| `filterable` | `boolean` |
| `pagination` | `boolean` |
| `rowActions` | `ReactNode (optional)` |

### States

- loading
- empty
- error

### Accessibility

- **role:** table
- **aria-label:** Table description required

### Example

```tsx
<DataTable columns={cols} data={rows} sortable />
```

---

## StatusBadge

**ID:** `COMP-005`
**Type:** badge

Status indicator for workflows, invoices and exceptions

### Variants

- `success`
- `warning`
- `error`
- `info`
- `neutral`

### Props

| Prop | Type |
|------|------|
| `label` | `string` |
| `variant` | `success | warning | error | info | neutral` |
| `icon` | `ReactNode (optional)` |

### States

- default

### Accessibility

- **role:** status
- **aria-label:** Status description

### Example

```tsx
<StatusBadge variant='success' label='Validated' />
```

---

## KpiCard

**ID:** `COMP-006`
**Type:** card

Card for KPI metrics on monitoring dashboard

### Variants

- `default`
- `accent`
- `outline`

### Props

| Prop | Type |
|------|------|
| `title` | `string` |
| `value` | `string | number` |
| `delta` | `string (optional)` |
| `trend` | `up | down | flat (optional)` |
| `icon` | `ReactNode (optional)` |

### States

- default
- loading

### Accessibility

- **role:** region
- **aria-label:** KPI card

### Example

```tsx
<KpiCard title='Invoices' value='1,240' delta='+6%' trend='up' />
```

---

## ChartCard

**ID:** `COMP-007`
**Type:** chart

Chart container for performance and monitoring visuals

### Variants

- `line`
- `bar`
- `area`

### Props

| Prop | Type |
|------|------|
| `title` | `string` |
| `data` | `ChartData` |
| `variant` | `line | bar | area` |
| `legend` | `boolean` |
| `height` | `number` |

### States

- loading
- empty
- error

### Accessibility

- **role:** img
- **aria-label:** Chart description

### Example

```tsx
<ChartCard title='Workflow Latency' variant='line' data={data} />
```

---

## ModalDialog

**ID:** `COMP-008`
**Type:** modal

Modal for confirmations and exception handling actions

### Variants

- `default`
- `danger`
- `info`

### Props

| Prop | Type |
|------|------|
| `title` | `string` |
| `open` | `boolean` |
| `onClose` | `() => void` |
| `footer` | `ReactNode (optional)` |
| `size` | `sm | md | lg` |

### States

- open
- closed

### Accessibility

- **role:** dialog
- **aria-modal:** true
- **aria-labelledby:** Modal title id

### Example

```tsx
<ModalDialog title='Resolve Exception' open onClose={...} />
```

---

## Tabs

**ID:** `COMP-009`
**Type:** navigation

Tabbed navigation for settings and monitoring sections

### Variants

- `default`
- `pill`
- `underline`

### Props

| Prop | Type |
|------|------|
| `tabs` | `Array<{label: string, value: string, icon?: ReactNode}>` |
| `value` | `string` |
| `onChange` | `(value: string) => void` |

### States

- default
- active
- disabled

### Accessibility

- **role:** tablist
- **aria-label:** Tabs label

### Example

```tsx
<Tabs tabs={tabs} value='company' onChange={setTab} />
```

---

## Stepper

**ID:** `COMP-010`
**Type:** progress

Multi-step progress indicator for onboarding flows (bank account, company settings)

### Variants

- `default`
- `compact`

### Props

| Prop | Type |
|------|------|
| `steps` | `Array<{label: string}>` |
| `currentStep` | `number` |
| `completed` | `number[] (optional)` |

### States

- default
- completed

### Accessibility

- **role:** progressbar
- **aria-valuenow:** currentStep
- **aria-valuemax:** steps.length

### Example

```tsx
<Stepper steps={steps} currentStep={2} />
```

---

## FileUpload

**ID:** `COMP-011`
**Type:** upload

Upload area for bulk customer import and document attachments

### Variants

- `dropzone`
- `button`

### Props

| Prop | Type |
|------|------|
| `accept` | `string` |
| `multiple` | `boolean` |
| `onUpload` | `(files: File[]) => void` |
| `maxSizeMb` | `number` |
| `helperText` | `string (optional)` |

### States

- idle
- dragging
- uploading
- error
- success

### Accessibility

- **role:** button
- **aria-label:** File upload

### Example

```tsx
<FileUpload accept='.csv' multiple onUpload={handleUpload} />
```

---

