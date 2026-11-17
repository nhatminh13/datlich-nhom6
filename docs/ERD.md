# Sơ đồ ERD

```mermaid
erDiagram
    users ||--o| staff : "là"
    users ||--o{ appointments : "đặt (khách hàng)"
    staff ||--o{ availabilities : "có ca làm"
    staff ||--o{ time_offs : "có thời gian nghỉ"
    staff ||--o{ appointments : "phục vụ"
    staff }o--o{ services : "staff_services"
    services ||--o{ appointments : "thuộc"
    appointments ||--o{ appointment_logs : "ghi nhật ký"
    users ||--o{ appointment_logs : "thực hiện"

    users { bigint id PK
            varchar username UK
            varchar password "băm PBKDF2"
            varchar role "CUSTOMER|STAFF|ADMIN"
            varchar phone }
    services { bigint id PK
               varchar name UK
               int duration_minutes "15..240"
               int price
               bool is_active }
    staff { bigint id PK
            bigint user_id FK,UK
            varchar title
            bool is_active }
    availabilities { bigint id PK
                     bigint staff_id FK
                     smallint weekday "0=Thứ 2..6=CN"
                     time start_time
                     time end_time "> start_time" }
    time_offs { bigint id PK
                bigint staff_id FK
                datetime start
                datetime end "> start"
                varchar reason }
    appointments { bigint id PK
                   bigint customer_id FK
                   bigint staff_id FK
                   bigint service_id FK
                   datetime start
                   datetime end "= start + duration"
                   varchar status "PENDING|CONFIRMED|COMPLETED|CANCELLED"
                   varchar note
                   varchar cancel_reason }
    appointment_logs { bigint id PK
                       bigint appointment_id FK
                       bigint actor_id FK
                       varchar action
                       varchar old_status
                       varchar new_status
                       datetime created_at }
```

## Quy tắc chống trùng lịch
Hai lịch hẹn A, B **đang hiệu lực** (PENDING/CONFIRMED) của cùng một nhân viên bị coi là chồng lấn khi
`A.start < B.end AND B.start < A.end`. Lịch nối tiếp (A.end = B.start) hợp lệ.

Khi đặt/đổi lịch, máy chủ mở giao dịch, khóa dòng nhân viên (`SELECT ... FOR UPDATE`), kiểm tra lại
giờ làm việc – thời gian nghỉ – chồng lấn, rồi mới lưu. Hai yêu cầu đồng thời vào cùng một thợ phải xếp hàng,
yêu cầu đến sau sẽ thấy lịch vừa được lưu và bị từ chối. Đổi lịch lỗi thì giao dịch không lưu gì, lịch cũ giữ nguyên.
