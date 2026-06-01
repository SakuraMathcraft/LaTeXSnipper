#pragma once

#include <string>

std::wstring ConsumePendingPayload();
void StoreEditorPayload(const std::wstring& payloadJson);
std::wstring ConsumeEditorPayloadResult();
