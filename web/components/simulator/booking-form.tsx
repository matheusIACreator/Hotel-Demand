"use client"

import type { FieldErrors, UseFormRegister } from "react-hook-form"

import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import type { Booking } from "@/lib/contract/booking"
import { FIELD_GROUPS, type FieldMeta } from "@/lib/contract/fields"

// As mensagens do schema começam pelo nome do campo, já visível no rótulo.
function fieldMessage(message?: string) {
  if (!message) return undefined
  const text = message.replace(/^[^:]{1,40}:\s*/, "")
  return text.charAt(0).toUpperCase() + text.slice(1)
}

const toNumber = (value: unknown) =>
  value === "" || value === null || value === undefined
    ? undefined
    : Number(value)

const toNullableNumber = (value: unknown) =>
  value === "" || value === null || value === undefined ? null : Number(value)

const toNullableString = (value: unknown) =>
  value === "" || value === null || value === undefined ? null : String(value)

function Control({
  field,
  register,
  invalid,
  describedBy,
}: {
  field: FieldMeta
  register: UseFormRegister<Booking>
  invalid: boolean
  describedBy?: string
}) {
  const common = {
    id: field.name,
    "aria-invalid": invalid || undefined,
    "aria-describedby": describedBy,
  }

  switch (field.kind) {
    case "integer":
      return (
        <Input
          {...common}
          type="number"
          inputMode="numeric"
          step={1}
          min={field.min}
          max={field.max}
          {...register(field.name, { setValueAs: toNumber })}
        />
      )
    case "decimal":
      return (
        <Input
          {...common}
          type="number"
          inputMode="decimal"
          step={field.step}
          min={field.min}
          max={field.max}
          {...register(field.name, { setValueAs: toNumber })}
        />
      )
    case "nullable-number":
      return (
        <Input
          {...common}
          type="number"
          inputMode="numeric"
          min={0}
          placeholder={field.emptyLabel}
          {...register(field.name, { setValueAs: toNullableNumber })}
        />
      )
    case "select":
      return (
        <NativeSelect {...common} className="w-full" {...register(field.name)}>
          <NativeSelectOption value="">Selecione…</NativeSelectOption>
          {field.options.map((o) => (
            <NativeSelectOption key={o.value} value={o.value}>
              {o.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )
    case "nullable-select":
      return (
        <NativeSelect
          {...common}
          className="w-full"
          {...register(field.name, { setValueAs: toNullableString })}
        >
          <NativeSelectOption value="">{field.emptyLabel}</NativeSelectOption>
          {field.options.map((o) => (
            <NativeSelectOption key={o.value} value={o.value}>
              {o.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )
    case "binary":
      return (
        <NativeSelect
          {...common}
          className="w-full"
          {...register(field.name, { setValueAs: toNumber })}
        >
          <NativeSelectOption value="0">Não</NativeSelectOption>
          <NativeSelectOption value="1">Sim</NativeSelectOption>
        </NativeSelect>
      )
  }
}

export function BookingFields({
  register,
  errors,
}: {
  register: UseFormRegister<Booking>
  errors: FieldErrors<Booking>
}) {
  return (
    <div className="space-y-6">
      {FIELD_GROUPS.map((group, index) => (
        <FieldSet
          key={group.id}
          id={`grupo-${group.id}`}
          className="gap-5 surface p-5 sm:p-6"
        >
          <div>
            <FieldLegend className="flex items-center gap-3 font-heading text-xl font-normal">
              <span
                className="flex size-7 items-center justify-center rounded-full bg-secondary font-sans text-sm font-medium tabular-nums"
                aria-hidden
              >
                {index + 1}
              </span>
              {group.title}
            </FieldLegend>
            <FieldDescription>{group.description}</FieldDescription>
          </div>
          <div className="grid gap-x-5 gap-y-5 sm:grid-cols-2">
            {group.fields.map((field) => {
              const message = fieldMessage(errors[field.name]?.message)
              const hintId = field.hint ? `${field.name}-dica` : undefined
              const errorId = message ? `${field.name}-erro` : undefined
              return (
                <Field key={field.name} data-invalid={!!message || undefined}>
                  <FieldLabel htmlFor={field.name}>
                    {field.label}
                    {field.unit ? (
                      <span className="font-normal text-muted-foreground">
                        ({field.unit})
                      </span>
                    ) : null}
                  </FieldLabel>
                  <Control
                    field={field}
                    register={register}
                    invalid={!!message}
                    describedBy={
                      [hintId, errorId].filter(Boolean).join(" ") || undefined
                    }
                  />
                  {field.hint ? (
                    <FieldDescription id={hintId} className="text-xs">
                      {field.hint}
                    </FieldDescription>
                  ) : null}
                  {message ? (
                    <FieldError id={errorId}>{message}</FieldError>
                  ) : null}
                </Field>
              )
            })}
          </div>
        </FieldSet>
      ))}
    </div>
  )
}
