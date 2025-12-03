-- 添加「襪子」到 category_enum
-- 如果已經存在則不會報錯

ALTER TYPE category_enum ADD VALUE IF NOT EXISTS '襪子';

-- 驗證
SELECT enum_range(NULL::category_enum);
