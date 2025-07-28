CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room VARCHAR(255),
    username VARCHAR(255),
    message TEXT,
    timestamp DATETIME
);

INSERT INTO messages (room, username, message, timestamp) VALUES
('general', 'Dori', 'Hello!', '2025-07-23 10:00:00'),
('general', 'Itay', 'Hi there!', '2025-07-23 10:01:00');
