#core/init_db.py
from app.core.db import Base, engine, get_db
from app.models.wardrobe import Wardrobe
from app.models.auth import User
from app.models.outfit import Outfit
from sqlalchemy import text

def init_db():
    Base.metadata.create_all(bind=engine)
    print("資料庫建立完成")

def init_virtual_fitting_tables():
    """初始化虚拟试衣功能所需的数据表"""
    db = next(get_db())
    
    try:
        print("\n开始创建虚拟试衣相关表...")
        
        # 创建 body_metrics 表
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS body_metrics (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                height_cm DECIMAL(5, 2),
                weight_kg DECIMAL(5, 2),
                chest_cm DECIMAL(5, 2),
                waist_cm DECIMAL(5, 2),
                hip_cm DECIMAL(5, 2),
                shoulder_cm DECIMAL(5, 2),
                shoe_size DECIMAL(4, 1),
                display_name VARCHAR(255),
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(user_id)
            );
        """))
        print("✓ body_metrics 表已创建")
        
        # 创建 posts 表
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                content TEXT,
                tags TEXT,
                clothing_ids TEXT,
                image_url TEXT,
                likes_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))
        print("✓ posts 表已创建")
        
        # 创建索引
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_body_metrics_user_id ON body_metrics(user_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);"))
        print("✓ 索引已创建")
        
        db.commit()
        print("\n✅ 虚拟试衣相关表已成功创建！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 创建表时出错: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    init_virtual_fitting_tables()