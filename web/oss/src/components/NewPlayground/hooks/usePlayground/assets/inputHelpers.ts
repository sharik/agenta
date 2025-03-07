import {hashMetadata} from "../../../assets/hash"
import {transformPrimitive} from "../../../assets/utilities/genericTransformer"
import type {
    EnhancedObjectConfig,
    ObjectMetadata,
    StringMetadata,
} from "../../../assets/utilities/genericTransformer/types"
import {generateId} from "../../../assets/utilities/genericTransformer/utilities/string"
import type {EnhancedVariant, Message} from "../../../assets/utilities/transformer/types"
import {PlaygroundStateData} from "../types"

/**
 * Variable Management
 * ------------------
 */

/**
 * Extract variables from a message string using fstring syntax {variableName}
 * @param input - Message content to extract variables from
 * @returns Array of variable names found in the string
 */
export function extractVariables(input: string): string[] {
    const variablePattern = /\{\{\s*(\w+)\s*\}\}/g
    const variables: string[] = []

    let match: RegExpExecArray | null
    while ((match = variablePattern.exec(input)) !== null) {
        variables.push(match[1])
    }

    return variables
}

/**
 * Schema Management
 * ----------------
 */

/**
 * Creates an input schema from a list of input keys
 * @param inputKeys - Array of input key names
 * @returns InputSchema with metadata for array of input rows
 */
export function createInputSchema(inputKeys: string[]): EnhancedVariant["inputs"]["__metadata"] {
    const properties: Record<string, StringMetadata> = Object.fromEntries(
        inputKeys.map((key) => [
            key,
            {
                type: "string",
                title: key,
                nullable: false,
                allowFreeform: true,
            },
        ]),
    )

    return {
        type: "array",
        title: "Input Rows",
        description: "Input values for variant execution",
        itemMetadata: {
            type: "object",
            title: "Input Row",
            description: "Single set of input values",
            properties,
            nullable: false,
        },
        nullable: false,
    }
}

/**
 * Input Row Management
 * -------------------
 */

/**
 * Creates a new input row with enhanced primitive values
 * Properties are spread at the root level instead of being nested under "value"
 */
export function createInputRow(
    inputKeys: string[],
    metadata: ObjectMetadata,
): EnhancedVariant["inputs"]["value"][number] {
    // Create enhanced values for each input key
    const enhancedValues = Object.fromEntries(
        inputKeys.map((key) => {
            const metadataHash = hashMetadata(metadata.properties[key])

            return [
                key,
                {
                    __id: generateId(),
                    __metadata: metadataHash,
                    value: "",
                },
            ]
        }),
    )

    const metadataHash = hashMetadata(metadata)

    // Return object with properties spread at root level and initialize __result as undefined
    return {
        __id: generateId(),
        __metadata: metadataHash,
        __result: undefined, // TODO: DEPRECATED
        __runs: {},
        ...enhancedValues,
    } as EnhancedVariant["inputs"]["value"][number]
}

/**
 * Prompt Key Management
 * --------------------
 */

/**
 * Updates input keys for a single prompt based on its messages
 * @param prompt - Prompt configuration to update
 * @returns Array of extracted variable names
 */
export function updatePromptInputKeys(prompt: EnhancedVariant["prompts"][number]) {
    const messagesContent = prompt.messages.value.map((message) => message.content.value || "")
    const variables = messagesContent.map((message) => extractVariables(message)).flat()

    if (prompt.inputKeys) {
        prompt.inputKeys.value = variables.map((variable) => {
            const existing = (prompt.inputKeys.value || []).find((key) => key.value === variable)
            return (
                existing ||
                transformPrimitive(
                    variable,
                    createInputSchema(variables).itemMetadata.properties[variable],
                )
            )
        })
    }

    return variables
}

/**
 * Updates input keys for all prompts in a variant
 * @param variant - Variant to update prompt input keys for
 * @returns Updated variant
 */
export function updateVariantPromptKeys(variant: EnhancedVariant) {
    variant.prompts?.forEach((prompt) => updatePromptInputKeys(prompt))
    return variant
}

/**
 * Variant Input Management
 * -----------------------
 */

/**
 * Initialize variant inputs with a single empty row
 * @param variant - Variant to initialize inputs for
 * @returns Updated variant with initialized inputs
 */
export function initializeVariantInputs(variant: EnhancedVariant) {
    const allInputKeys = Array.from(
        new Set(variant.prompts.flatMap((prompt) => prompt.inputKeys?.value || [])),
    )

    const inputStrings = Array.from(allInputKeys).map((enhancedKey) => enhancedKey.value)
    const inputSchema = createInputSchema(inputStrings)
    const initialInputRow = createInputRow(inputStrings, inputSchema.itemMetadata)

    const metadataHash = hashMetadata(inputSchema)

    variant.inputs = {
        __id: generateId(),
        __metadata: metadataHash,
        value: [initialInputRow],
    }

    return variant
}

/**
 * Synchronizes variant inputs structure with current prompt variables
 */
export function syncVariantInputs(
    variants: EnhancedVariant[],
    generationInputData: PlaygroundStateData["generationData"]["inputs"],
) {
    const currentInputKeys = new Set(
        variants.flatMap((variant) =>
            variant.prompts.flatMap((prompt) => prompt.inputKeys?.value || []),
        ),
    )

    const inputStrings = Array.from(currentInputKeys).map((enhancedKey) => enhancedKey.value)

    const inputSchema = createInputSchema(inputStrings)

    const existingInputsId = generationInputData?.__id || generateId()

    // Create metadata with ID properly typed
    const metadata = {
        ...inputSchema,
        __id: existingInputsId,
    }

    // Update each row while preserving all IDs
    const updatedRows = (generationInputData?.value || []).map((row) => {
        const keys = [...inputStrings] as const
        const metadataHash = hashMetadata(metadata.itemMetadata)

        const newRow = {
            __id: row.__id,
            __metadata: metadataHash,
            __result: row.__runs,
            __runs: row.__runs,
        } as PlaygroundStateData["generationData"]["inputs"]["value"][number]

        // For each current input key
        keys.forEach((key) => {
            if (key in row) {
                // If key existed before, preserve entire value object including ID
                if (!!key && row[key]) {
                    const _key = key as keyof typeof newRow
                    if (typeof _key === "string") {
                        newRow[_key] = row[_key]
                    }
                }
            } else {
                // Only create new ID for truly new keys
                const _key = key as keyof typeof newRow

                const metadataHash = hashMetadata(inputSchema.itemMetadata.properties[key])

                if (typeof _key === "string") {
                    newRow[_key] = {
                        __id: generateId(),
                        __metadata: metadataHash,
                    } as PlaygroundStateData["generationData"]["inputs"]["value"][number][typeof _key]
                }
            }
        })

        return newRow
    })

    // Ensure at least one row exists
    if (updatedRows.length === 0) {
        updatedRows.push(createInputRow(inputStrings, inputSchema.itemMetadata))
    }

    const metadataHash = hashMetadata(metadata)

    generationInputData = {
        __id: existingInputsId,
        __metadata: metadataHash,
        value: updatedRows,
    }

    return generationInputData
}

export function syncVariantMessages(
    variants: EnhancedVariant[],
    generationMessageData: PlaygroundStateData["generationData"]["messages"],
) {
    if (!generationMessageData.value) return generationMessageData

    const promptMessages = variants.flatMap((variant) =>
        variant.prompts.flatMap((prompt) => prompt.messages.value || []),
    )
    const generationMessages = generationMessageData.value.map((data) => data.value)

    const syncVariantData = (arr1: any[], arr2: any[]) => {
        let lastMatchIndex = -1

        arr2.forEach((item2) => {
            const indexInArr1 = arr1.findIndex((item1) => item1.__id === item2.__id)

            if (indexInArr1 !== -1) {
                arr1[indexInArr1] = {...arr1[indexInArr1], ...item2}
                lastMatchIndex = Math.max(lastMatchIndex, indexInArr1)
            } else {
                const insertIndex = lastMatchIndex + 1
                arr1.splice(insertIndex, 0, item2)
                lastMatchIndex = insertIndex
            }
        })

        return arr1
    }

    const result = syncVariantData(generationMessages, promptMessages)

    const transform = result.map((r) => ({
        __id: generateId(),
        __metadata: r.__metadata,
        __disabled: r.__disabled,
        value: r,
    }))

    generationMessageData = {
        ...generationMessageData,
        value: transform,
    }

    return generationMessageData
}

/**
 * Gets the current input keys from all prompts in a variant
 * @param variant - Variant to get input keys from
 * @returns Set of unique input keys
 */
export function getVariantInputKeys(variant: EnhancedVariant): string[] {
    const inputKeys = new Set(
        variant.prompts?.flatMap((prompt) => prompt.inputKeys?.value || []) || [],
    )
    return Array.from(new Set(Array.from(inputKeys).map((key) => key.value)))
}

/**
 * Gets the current messages from all prompts in a variant
 * @param variant - Variant to get input keys from
 * @returns Array of messages
 */
export function getVariantMessages(variant: EnhancedVariant): EnhancedObjectConfig<Message>[] {
    return variant.prompts.flatMap((prompt) => prompt.messages.value)
}
