#pragma once

#include "Presentation.h"

#include <objidl.h>

HRESULT SavePresentationToStorage(IStorage* storage, const FormulaPresentation& presentation);
HRESULT LoadPresentationFromStorage(IStorage* storage, FormulaPresentation* presentation);
