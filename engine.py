import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def calculate_quote(job_data, price_registry):
    """
    Calculates a window cleaning quote based on a specific pricing profile.
    Supports per-floor custom rate overrides, per-addon custom rate overrides, and tax rate overrides.
    """
    # 1. Profile Selection
    profile_id = job_data.get('profile_id', 'Residential_Standard')
    profiles = price_registry.get('profiles', {})
    
    if profile_id not in profiles:
        raise ValueError(f"Invalid pricing profile: {profile_id}")
    
    price_sheet = profiles[profile_id]

    # 2. Schema Validation
    required_keys = {
        'base_pane_rate': (float, int, Decimal),
        'base_callout_fee': (float, int, Decimal),
        'tax_rate': (float, int, Decimal),
        'story_surcharges': dict,
        'add_on_rates': dict
    }
    
    for key, expected_type in required_keys.items():
        if key not in price_sheet:
            raise ValueError(f"Profile '{profile_id}' is missing required key: {key}")
        if not isinstance(price_sheet[key], expected_type):
            raise ValueError(f"Invalid type for {key} in profile '{profile_id}': Expected {expected_type}, got {type(price_sheet[key])}")

    # Convert rates to Decimal for precision
    base_rate = Decimal(str(price_sheet['base_pane_rate']))
    callout_fee = Decimal(str(price_sheet['base_callout_fee']))
    
    # Tax Rate Handling: Use override if provided, otherwise use profile default
    tax_override = job_data.get('tax_override')
    if tax_override:
        try:
            tax_rate = Decimal(str(tax_override))
            is_tax_overridden = True
        except Exception:
            raise ValueError(f"Invalid tax override rate: {tax_override}")
    else:
        tax_rate = Decimal(str(price_sheet['tax_rate']))
        is_tax_overridden = False
    
    surcharges = {k: Decimal(str(v)) for k, v in price_sheet['story_surcharges'].items()}
    addon_rates = {k: Decimal(str(v)) for k, v in price_sheet['add_on_rates'].items()}

    # Input Validation
    panes_per_floor = job_data.get('panes', {})
    if not isinstance(panes_per_floor, dict):
        raise ValueError("job_data['panes'] must be a dictionary of floor: count.")
    
    for floor, count in panes_per_floor.items():
        if count < 0:
            raise ValueError(f"Pane count for {floor} cannot be negative.")

    add_ons = job_data.get('add_ons', [])
    if not isinstance(add_ons, list):
        raise ValueError("job_data['add_ons'] must be a list of strings.")
        
    overrides = job_data.get('overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError("job_data['overrides'] must be a dictionary of floor: rate.")

    addon_overrides = job_data.get('addon_overrides', {})
    if not isinstance(addon_overrides, dict):
        raise ValueError("job_data['addon_overrides'] must be a dictionary of addon: rate.")

    # 3. Calculate Costs and Generate Line Items
    line_items = []
    subtotal_panes = Decimal('0.00')
    total_panes = 0
    
    for floor, count in panes_per_floor.items():
        # Check for custom rate override
        if floor in overrides and overrides[floor]:
            try:
                rate = Decimal(str(overrides[floor]))
                is_overridden = True
            except Exception:
                raise ValueError(f"Invalid override rate for {floor}: {overrides[floor]}")
        else:
            multiplier = surcharges.get(floor, Decimal('1.0'))
            rate = base_rate * multiplier
            is_overridden = False
            
        cost = Decimal(str(count)) * rate
        subtotal_panes += cost
        total_panes += count
        
        line_items.append({
            "description": f"{floor.replace('floor', 'Floor ')} - {count} Panes {'(Custom Rate)' if is_overridden else ''}",
            "cost": cost
        })

    subtotal_addons = Decimal('0.00')
    for addon in add_ons:
        # Check for custom addon rate override
        if addon in addon_overrides and addon_overrides[addon]:
            try:
                rate = Decimal(str(addon_overrides[addon]))
                is_overridden = True
            except Exception:
                raise ValueError(f"Invalid override rate for addon {addon}: {addon_overrides[addon]}")
        else:
            rate = addon_rates.get(addon, Decimal('0.00'))
            is_overridden = False
            
        cost = Decimal(str(total_panes)) * rate
        subtotal_addons += cost
        line_items.append({
            "description": f"Add-on: {addon} {'(Custom Rate)' if is_overridden else ''}",
            "cost": cost
        })

    # 4. Sum and Apply Callout Fee
    running_total = subtotal_panes + subtotal_addons
    final_before_tax = max(callout_fee, running_total)

    # 5. Calculate Tax
    tax_amount = final_before_tax * tax_rate
    grand_total = final_before_tax + tax_amount

    # 6. Snapshotting
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "profile_id": profile_id,
        "input": {
            "panes": panes_per_floor,
            "add_ons": add_ons,
            "overrides": overrides,
            "addon_overrides": addon_overrides,
            "tax_override": tax_override
        },
        "pricing_applied": {
            "base_pane_rate": base_rate,
            "base_callout_fee": callout_fee,
            "tax_rate": tax_rate,
            "tax_overridden": is_tax_overridden,
            "story_surcharges": surcharges,
            "add_on_rates": addon_rates
        },
        "line_items": line_items,
        "calculation": {
            "subtotal_panes": subtotal_panes.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "subtotal_addons": subtotal_addons.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "final_before_tax": final_before_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "tax_amount": tax_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            "grand_total": grand_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        }
    }

    return snapshot
