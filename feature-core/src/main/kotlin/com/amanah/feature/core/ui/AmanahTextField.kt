package com.amanah.feature.core.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation

/**
 * Standard Amanah outlined text field.
 *
 *   - Always full-width.
 *   - Single-line by default; pass `singleLine = false` for multi-line.
 *   - Optional leading icon.
 *   - Optional [errorText]; when non-null switches into error appearance.
 *   - Pass [isPassword] = true to apply [PasswordVisualTransformation].
 */
@Composable
fun AmanahTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    leadingIcon: ImageVector? = null,
    trailingContent: @Composable (() -> Unit)? = null,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    singleLine: Boolean = true,
    enabled: Boolean = true,
    errorText: String? = null,
    isPassword: Boolean = false,
    passwordVisible: Boolean = false,
) {
    OutlinedTextField(
        value             = value,
        onValueChange     = onValueChange,
        label             = { Text(label) },
        leadingIcon       = if (leadingIcon != null) { { Icon(leadingIcon, contentDescription = null) } } else null,
        trailingIcon      = trailingContent,
        isError           = errorText != null,
        supportingText    = errorText?.let { { Text(it) } },
        keyboardOptions   = KeyboardOptions(keyboardType = keyboardType, imeAction = imeAction),
        keyboardActions   = keyboardActions,
        visualTransformation = if (isPassword && !passwordVisible) PasswordVisualTransformation() else VisualTransformation.None,
        singleLine        = singleLine,
        enabled           = enabled,
        modifier          = modifier.fillMaxWidth(),
    )
}
